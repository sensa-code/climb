#!/usr/bin/env python3
"""
獸醫文章自動化擷取工具
===========================
三層策略：Jina Reader（首選）→ BeautifulSoup（備選）→ Playwright（兜底）
支援平台：PTT、Medium、新聞網站、部落格、獸醫學會網站等

用法：
  # 單一 URL
  python scraper.py https://example.com/article

  # 批次（從檔案讀取 URL 列表）
  python scraper.py --batch urls.txt

  # 指定輸出目錄
  python scraper.py https://example.com/article --output ./my_articles
"""

import os
import re
import sys
import json
import time
import hashlib
import argparse
import logging
import urllib.robotparser
import urllib.request
import urllib.error
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md

# ============================================================
# 設定
# ============================================================

# 預設值（可被 config.json 覆蓋）
_DEFAULTS = {
    "output_dir": os.path.expanduser("~/vet-articles"),
    "request_timeout": 30,
    "max_retries": 3,
    "retry_base_delay": 2,
    "politeness_delay": 2,
    "jina_base_url": "https://r.jina.ai/",
    "log_level": "INFO",
}


def load_config(config_path: str = None) -> dict:
    """載入設定檔，未找到則用預設值"""
    config = dict(_DEFAULTS)
    if config_path is None:
        config_path = Path(__file__).parent / "config.json"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            config.update(user_config)
            # 展開 ~ 路徑
            if "output_dir" in user_config:
                config["output_dir"] = os.path.expanduser(config["output_dir"])
        except (json.JSONDecodeError, TypeError):
            pass  # 設定檔損壞時使用預設值

    return config


# 載入設定（模組層級，供各函式使用）
_CONFIG = load_config()

DEFAULT_OUTPUT_DIR = _CONFIG["output_dir"]
REQUEST_TIMEOUT = _CONFIG["request_timeout"]
JINA_BASE_URL = _CONFIG["jina_base_url"]
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")  # 設定後可提升至 200 次/分鐘
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'}
MAX_RETRIES = _CONFIG["max_retries"]
RETRY_BASE_DELAY = _CONFIG["retry_base_delay"]
POLITENESS_DELAY = _CONFIG["politeness_delay"]
DEDUP_FILE = ".fetched_urls.json"  # 已下載 URL 記錄檔

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
}

logger = logging.getLogger(__name__)


def _setup_logging(log_dir: str = None, level: str = "INFO"):
    """設定 console + file 雙輸出日誌"""
    logger.setLevel(logging.DEBUG)

    # 避免重複添加 handler
    if logger.handlers:
        return logger

    # Console handler（保持原有行為）
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%H:%M:%S'))
    logger.addHandler(console)

    # File handler（DEBUG 等級，按日期分檔）
    if log_dir:
        log_path = Path(log_dir) / "logs"
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = log_path / f"scraper_{datetime.now().strftime('%Y%m%d')}.log"

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s - %(message)s'
        ))
        logger.addHandler(file_handler)

    return logger


# ============================================================
# robots.txt 檢查
# ============================================================

@lru_cache(maxsize=128)
def _get_robots_parser(domain: str):
    """取得並快取指定 domain 的 robots.txt 解析器"""
    robots_url = f"{domain}/robots.txt"
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        resp = urllib.request.urlopen(robots_url, timeout=5)
        content = resp.read().decode("utf-8", errors="surrogateescape")
        parser.parse(content.splitlines())
        return parser
    except Exception:
        return None


def is_allowed_by_robots(url: str, user_agent: str = "*") -> bool:
    """檢查 robots.txt 是否允許擷取此 URL（fail-open：無法取得時允許）"""
    try:
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        parser = _get_robots_parser(domain)
        if parser is None:
            return True
        return parser.can_fetch(user_agent, url)
    except Exception:
        return True


# ============================================================
# 重試機制（指數退避）
# ============================================================

def retry_fetch(func, url: str, max_retries: int = MAX_RETRIES) -> dict | None:
    """帶指數退避的重試包裝器"""
    for attempt in range(max_retries):
        result = func(url)
        if result is not None:
            return result
        if attempt < max_retries - 1:
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            logger.info(f"  第 {attempt + 1} 次失敗，{delay} 秒後重試...")
            time.sleep(delay)
    return None


# ============================================================
# 去重機制
# ============================================================

def _load_dedup_record(output_dir: str) -> set:
    """載入已下載的 URL 記錄"""
    dedup_path = Path(output_dir) / DEDUP_FILE
    if dedup_path.exists():
        try:
            data = json.loads(dedup_path.read_text(encoding='utf-8'))
            return set(data)
        except (json.JSONDecodeError, TypeError):
            return set()
    return set()


def _save_dedup_record(output_dir: str, fetched_urls: set):
    """儲存已下載的 URL 記錄"""
    dedup_path = Path(output_dir) / DEDUP_FILE
    dedup_path.parent.mkdir(parents=True, exist_ok=True)
    dedup_path.write_text(
        json.dumps(sorted(fetched_urls), ensure_ascii=False, indent=2),
        encoding='utf-8'
    )


def is_already_fetched(url: str, output_dir: str) -> bool:
    """檢查 URL 是否已經下載過"""
    fetched = _load_dedup_record(output_dir)
    return url in fetched


def mark_as_fetched(url: str, output_dir: str):
    """將 URL 標記為已下載"""
    fetched = _load_dedup_record(output_dir)
    fetched.add(url)
    _save_dedup_record(output_dir, fetched)


# ============================================================
# YAML 安全轉義
# ============================================================

def _yaml_safe_title(title: str) -> str:
    """確保標題可安全放入 YAML frontmatter"""
    title = title.replace('\\', '\\\\').replace('"', '\\"')
    return title


# ============================================================
# 第一步：平台識別
# ============================================================

PLATFORM_RULES = [
    # (名稱, 域名關鍵字列表, 是否需要登入, 建議策略)
    ("PTT",        ["ptt.cc"],                          False, "jina"),
    ("Medium",     ["medium.com"],                      False, "jina"),
    ("痞客邦",     ["pixnet.net"],                       False, "jina"),
    ("方格子",     ["vocus.cc"],                         False, "jina"),
    ("LINE TODAY", ["today.line.me"],                    False, "jina"),
    ("獸醫學會",   ["vetmed.org.tw", "tava.org.tw",
                    "avat.org.tw"],                      False, "bs4"),
    ("新聞網站",   ["udn.com", "ltn.com.tw",
                    "ettoday.net", "setn.com",
                    "chinatimes.com", "tvbs.com.tw",
                    "cna.com.tw"],                       False, "jina"),
    ("部落格",     ["blogspot.com", "wordpress.com",
                    "blog."],                            False, "jina"),
    # 難爬平台（提醒用戶使用 Chrome Extension）
    ("Facebook",   ["facebook.com", "fb.com",
                    "fb.watch"],                         True,  "skip"),
    ("Instagram",  ["instagram.com"],                   True,  "skip"),
    ("微信公眾號", ["mp.weixin.qq.com"],                 True,  "playwright"),
    ("小紅書",     ["xiaohongshu.com", "xhslink.com"],  True,  "playwright"),
]


def identify_platform(url: str) -> dict:
    """識別 URL 所屬平台，回傳平台資訊"""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    for name, keywords, needs_login, strategy in PLATFORM_RULES:
        for kw in keywords:
            if kw in domain:
                return {
                    "name": name,
                    "domain": domain,
                    "needs_login": needs_login,
                    "strategy": strategy,
                }

    # 未知平台，預設用 Jina
    return {
        "name": "其他",
        "domain": domain,
        "needs_login": False,
        "strategy": "jina",
    }


# ============================================================
# 第二步：Jina Reader 策略（首選，免費）
# ============================================================

def fetch_with_jina(url: str) -> dict | None:
    """用 Jina Reader 擷取網頁，回傳 Markdown 內容"""
    jina_url = f"{JINA_BASE_URL}{url}"
    headers = {
        **HEADERS,
        'Accept': 'text/markdown',
    }
    if JINA_API_KEY:
        headers['Authorization'] = f'Bearer {JINA_API_KEY}'

    try:
        logger.info(f"[Jina] 正在擷取：{url}")
        resp = requests.get(jina_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()

        content = resp.text.strip()

        # 驗證內容有效性
        if len(content) < 100:
            logger.warning("[Jina] 內容太短，可能擷取失敗")
            return None

        # 嘗試從內容提取標題（Jina 通常第一行是 Title:）
        title = _extract_title_from_jina(content)

        return {
            "title": title,
            "content": content,
            "source": "jina",
            "url": url,
        }

    except requests.exceptions.RequestException as e:
        logger.warning(f"[Jina] 擷取失敗：{e}")
        return None


def _extract_title_from_jina(content: str) -> str:
    """從 Jina 回傳的內容提取標題"""
    lines = content.split('\n')
    for line in lines[:5]:
        line = line.strip()
        # Jina 格式：Title: xxxxx
        if line.startswith('Title:'):
            return line[6:].strip()
        # Markdown H1
        if line.startswith('# '):
            return line[2:].strip()
    return "未命名文章"


# ============================================================
# 第三步：HTML 解析（BS4 和 Playwright 共用）
# ============================================================

def _parse_ptt_article(soup, url: str, source: str = "bs4") -> dict | None:
    """PTT 專用解析器 — 處理 #main-content 結構"""
    main = soup.find('div', id='main-content')
    if not main:
        return None

    # 提取 meta 資訊（作者、看板、標題、時間）
    meta = {}
    for metaline in main.select('div.article-metaline'):
        tag = metaline.select_one('span.article-meta-tag')
        value = metaline.select_one('span.article-meta-value')
        if tag and value:
            meta[tag.get_text(strip=True)] = value.get_text(strip=True)

    title = meta.get('標題', '')

    # 移除 metaline 和推文，只留正文
    for tag in main.select('div.article-metaline, div.article-metaline-right, '
                           'div.push, span.f2'):
        tag.decompose()

    # 取得正文（PTT 正文是 #main-content 內的文字節點）
    content = main.get_text(separator='\n').strip()

    # 清理：移除前後多餘的空行
    lines = content.splitlines()
    # 移除開頭的空行
    while lines and not lines[0].strip():
        lines.pop(0)
    # 移除結尾的 "--" 分隔線及之後的內容（通常是簽名檔）
    for i, line in enumerate(lines):
        if line.strip() == '--':
            lines = lines[:i]
            break
    content = '\n'.join(lines).strip()

    # 提取圖片
    images = []
    for img in main.find_all('img'):
        src = img.get('src') or img.get('data-src')
        if src:
            images.append(urljoin(url, src))

    # 也從文字中找圖片連結（PTT 常用 imgur 等直連）
    for line in content.splitlines():
        line = line.strip()
        if re.match(r'https?://\S+\.(jpg|jpeg|png|gif|webp)', line, re.I):
            if line not in images:
                images.append(line)

    if not content or len(content) < 30:
        return None

    return {
        "title": title or "未命名文章",
        "content": content,
        "source": source,
        "url": url,
        "images": images,
        "meta": meta,
    }


def _parse_html_to_article(html: str, url: str, source: str = "bs4") -> dict | None:
    """將 HTML 解析為 article dict（BS4 和 Playwright 共用）"""
    soup = BeautifulSoup(html, 'html.parser')

    # PTT 專用解析
    parsed = urlparse(url)
    if 'ptt.cc' in parsed.netloc:
        result = _parse_ptt_article(soup, url, source)
        if result:
            return result
        # 如果 PTT 專用解析失敗，繼續用通用邏輯

    # 移除不需要的元素
    for tag in soup.find_all(['script', 'style', 'nav', 'footer',
                               'header', 'aside', 'iframe', 'noscript']):
        tag.decompose()

    # 嘗試找到主要內容區域
    article = (
        soup.find('article') or
        soup.find('div', class_=re.compile(r'article|content|post|entry', re.I)) or
        soup.find('div', id=re.compile(r'article|content|post|entry', re.I)) or
        soup.find('main') or
        soup.body
    )

    if not article:
        logger.warning(f"[{source}] 找不到主要內容")
        return None

    # 轉換成 Markdown
    content = md(str(article), heading_style="ATX", strip=['img'])

    # 提取圖片
    images = []
    for img in article.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if src:
            full_url = urljoin(url, src)
            images.append(full_url)

    # 重建含圖片的 Markdown
    for i, img_url in enumerate(images):
        content += f"\n\n![圖片{i+1}]({img_url})"

    # 提取標題
    title = ""
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)
    h1 = soup.find('h1')
    if h1:
        title = h1.get_text(strip=True)

    if len(content.strip()) < 50:
        logger.warning(f"[{source}] 內容太短")
        return None

    return {
        "title": title or "未命名文章",
        "content": content.strip(),
        "source": source,
        "url": url,
    }


def fetch_with_bs4(url: str) -> dict | None:
    """用 requests + BeautifulSoup 擷取網頁"""
    try:
        logger.info(f"[BS4] 正在擷取：{url}")
        # PTT 需要 over18 cookie 才能存取內容
        cookies = {}
        parsed = urlparse(url)
        if 'ptt.cc' in parsed.netloc:
            cookies['over18'] = '1'
        resp = requests.get(url, headers=HEADERS, cookies=cookies,
                            timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or 'utf-8'
        return _parse_html_to_article(resp.text, url, source="bs4")

    except requests.exceptions.RequestException as e:
        logger.warning(f"[BS4] 擷取失敗：{e}")
        return None


# ============================================================
# 第三步之二：Playwright 策略（兜底，處理 JS 渲染頁面）
# ============================================================

def fetch_with_playwright(url: str) -> dict | None:
    """用 Playwright 無頭瀏覽器擷取 JS 渲染頁面"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[Playwright] 未安裝 playwright，跳過此策略")
        return None

    try:
        logger.info(f"[Playwright] 正在擷取：{url}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS['User-Agent'],
                locale='zh-TW'
            )

            # PTT 需要 over18 cookie
            parsed = urlparse(url)
            if 'ptt.cc' in parsed.netloc:
                context.add_cookies([{
                    'name': 'over18',
                    'value': '1',
                    'domain': '.ptt.cc',
                    'path': '/',
                }])

            page = context.new_page()
            page.goto(url, timeout=30000, wait_until='networkidle')
            html = page.content()
            browser.close()

        return _parse_html_to_article(html, url, source="playwright")

    except Exception as e:
        logger.warning(f"[Playwright] 擷取失敗：{e}")
        return None


# ============================================================
# 第四步：自動降級擷取
# ============================================================

def fetch_article(url: str) -> dict | None:
    """
    自動識別平台並用最佳策略擷取文章。
    含 robots.txt 檢查、重試機制、降級順序：Jina → BS4 → Playwright
    """
    platform = identify_platform(url)
    logger.info(f"平台識別：{platform['name']} ({platform['domain']})")

    # 需要登入的平台，提醒用戶
    if platform["strategy"] == "skip":
        logger.warning(
            f"⚠️  {platform['name']} 需要登入才能擷取，"
            f"建議使用 Chrome Extension 手動儲存！"
        )
        return None

    # robots.txt 檢查
    if not is_allowed_by_robots(url):
        logger.warning(f"🚫 robots.txt 不允許擷取：{url}")
        return None

    # 根據建議策略決定嘗試順序
    if platform["strategy"] == "playwright":
        strategies = [("playwright", fetch_with_playwright), ("bs4", fetch_with_bs4)]
    elif platform["strategy"] == "bs4":
        strategies = [("bs4", fetch_with_bs4), ("jina", fetch_with_jina)]
    else:
        strategies = [("jina", fetch_with_jina), ("bs4", fetch_with_bs4)]

    # Playwright 作為所有策略的最終兜底
    if ("playwright", fetch_with_playwright) not in strategies:
        strategies.append(("playwright", fetch_with_playwright))

    for name, func in strategies:
        result = retry_fetch(func, url)
        if result:
            logger.info(f"✅ 成功擷取（策略：{name}）")
            result["platform"] = platform["name"]
            return result
        logger.info(f"[{name}] 所有重試均失敗，嘗試下一個策略...")

    logger.error(f"❌ 所有策略都失敗：{url}")
    return None


# ============================================================
# 第五步：圖片下載與內容保存
# ============================================================

def download_image(img_url: str, save_path: Path, referer: str = "") -> bool:
    """下載單張圖片"""
    try:
        headers = {**HEADERS}
        if referer:
            headers['Referer'] = referer

        resp = requests.get(img_url, headers=headers, timeout=15, stream=True)
        resp.raise_for_status()

        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True

    except Exception as e:
        logger.warning(f"圖片下載失敗：{img_url} — {e}")
        return False


def save_article(article: dict, output_dir: str = DEFAULT_OUTPUT_DIR) -> Path:
    """
    儲存文章為 Markdown，下載圖片到本地。
    目錄結構：output_dir/YYYY-MM-DD_標題/content.md
    """
    title = article["title"]
    # 清理標題中的特殊字元
    safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)[:60]
    date_str = datetime.now().strftime("%Y-%m-%d")
    folder_name = f"{date_str}_{safe_title}"

    # 防止標題碰撞：資料夾已存在時加上短 hash
    article_dir = Path(output_dir) / folder_name
    if article_dir.exists():
        url_hash = hashlib.md5(article.get("url", "").encode()).hexdigest()[:6]
        folder_name = f"{folder_name}_{url_hash}"
        article_dir = Path(output_dir) / folder_name
    images_dir = article_dir / "images"
    article_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(exist_ok=True)

    content = article["content"]

    # 提取並下載圖片
    img_pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
    img_matches = re.findall(img_pattern, content)

    # 也找純 URL 圖片
    url_pattern = r'(https?://[^\s<>"\']+\.(?:jpg|jpeg|png|gif|webp)(?:\?[^\s<>"\']*)?)'
    url_matches = re.findall(url_pattern, content)

    all_images = []
    for alt, url in img_matches:
        all_images.append(url)
    for url in url_matches:
        if url not in all_images:
            all_images.append(url)

    # 決定 Referer
    referer = article.get("url", "")
    parsed = urlparse(referer)
    referer_base = f"{parsed.scheme}://{parsed.netloc}/"

    # 下載圖片並替換路徑
    for i, img_url in enumerate(all_images, 1):
        ext = _guess_extension(img_url)
        local_name = f"img_{i:02d}{ext}"
        local_path = images_dir / local_name

        if download_image(img_url, local_path, referer=referer_base):
            # 替換內容中的圖片路徑
            content = content.replace(img_url, f"images/{local_name}")
            logger.info(f"  📷 圖片 {i}: {local_name}")

    # 組裝最終 Markdown（YAML 安全轉義標題）
    yaml_title = _yaml_safe_title(title)
    metadata = f"""---
title: "{yaml_title}"
source: {article.get('url', 'N/A')}
platform: {article.get('platform', 'unknown')}
fetched_by: {article.get('source', 'unknown')}
date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
---

"""
    final_content = metadata + content

    # 儲存
    md_path = article_dir / "content.md"
    md_path.write_text(final_content, encoding='utf-8')

    # 同時儲存原始 JSON（方便後續批次處理）
    meta_path = article_dir / "metadata.json"
    meta_path.write_text(json.dumps({
        "title": title,
        "url": article.get("url"),
        "platform": article.get("platform"),
        "source": article.get("source"),
        "fetched_at": datetime.now().isoformat(),
        "image_count": len(all_images),
    }, ensure_ascii=False, indent=2), encoding='utf-8')

    logger.info(f"💾 已儲存：{md_path}")
    return article_dir


def _guess_extension(url: str) -> str:
    """從 URL 猜測圖片副檔名"""
    parsed = urlparse(url)
    path = parsed.path.lower()
    for ext in IMAGE_EXTENSIONS:
        if path.endswith(ext):
            return ext
    return '.jpg'  # 預設


# ============================================================
# 第六步：批次處理
# ============================================================

def batch_fetch_urls(urls: list, output_dir: str = DEFAULT_OUTPUT_DIR) -> dict:
    """
    處理 URL 列表的批次擷取。
    供 batch_fetch()、fetch_ptt_board() 等共用。
    """
    logger.info(f"共 {len(urls)} 個 URL 待擷取")

    results = {"success": [], "failed": [], "skipped": []}

    for i, url in enumerate(urls, 1):
        logger.info(f"\n--- [{i}/{len(urls)}] ---")

        # 去重檢查
        if is_already_fetched(url, output_dir):
            logger.info(f"已下載過，跳過：{url}")
            results["skipped"].append({"url": url, "reason": "已下載過"})
            continue

        platform = identify_platform(url)
        if platform["strategy"] == "skip":
            logger.warning(f"跳過 {platform['name']} 平台：{url}")
            results["skipped"].append({"url": url, "reason": f"{platform['name']} 需要登入"})
            continue

        article = fetch_article(url)
        if article:
            save_path = save_article(article, output_dir)
            mark_as_fetched(url, output_dir)
            results["success"].append({"url": url, "path": str(save_path)})
        else:
            results["failed"].append({"url": url})

        # 禮貌延遲，避免被封
        if i < len(urls):
            time.sleep(POLITENESS_DELAY)

    # 輸出統計
    logger.info(f"\n{'='*50}")
    logger.info(f"擷取完成！")
    logger.info(f"   成功：{len(results['success'])}")
    logger.info(f"   失敗：{len(results['failed'])}")
    logger.info(f"   跳過：{len(results['skipped'])}")

    # 儲存報告
    report_path = Path(output_dir) / f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    logger.info(f"   報告：{report_path}")

    return results


def batch_fetch(url_file: str, output_dir: str = DEFAULT_OUTPUT_DIR) -> dict:
    """
    從檔案讀取 URL 列表，批次擷取。
    URL 檔案格式：每行一個 URL，# 開頭為註解
    """
    urls = []
    with open(url_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)

    return batch_fetch_urls(urls, output_dir)


# ============================================================
# 第七步：PTT 看板列表頁爬取
# ============================================================

def fetch_ptt_board(board: str, pages: int = 1, output_dir: str = DEFAULT_OUTPUT_DIR) -> list:
    """
    從 PTT 看板列表頁提取文章 URL，支援翻頁。

    Args:
        board: 看板名稱（如 'cat', 'dog', 'Vet'）
        pages: 要爬取的頁數（從最新頁往回）
        output_dir: 輸出目錄（用於去重檢查）
    Returns:
        去重後的文章 URL 列表
    """
    base_url = f"https://www.ptt.cc/bbs/{board}/index.html"
    cookies = {'over18': '1'}
    collected_urls = []
    current_url = base_url

    for page_num in range(pages):
        logger.info(f"[PTT] 正在讀取看板 {board} 第 {page_num + 1}/{pages} 頁...")
        try:
            resp = requests.get(current_url, headers=HEADERS, cookies=cookies,
                                timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning(f"[PTT] 看板頁面讀取失敗：{e}")
            break

        soup = BeautifulSoup(resp.text, 'html.parser')

        # 提取文章連結
        for entry in soup.select('div.r-ent'):
            link = entry.select_one('div.title a')
            if link and link.get('href'):
                full_url = urljoin('https://www.ptt.cc', link['href'])
                if not is_already_fetched(full_url, output_dir):
                    collected_urls.append(full_url)

        # 找上一頁連結
        prev_link = None
        for btn in soup.select('div.btn-group-paging a.btn.wide'):
            if '上頁' in btn.text:
                prev_link = urljoin('https://www.ptt.cc', btn['href'])
                break

        if not prev_link or page_num >= pages - 1:
            break
        current_url = prev_link
        time.sleep(1)  # 禮貌延遲

    logger.info(f"[PTT] 從 {board} 看板取得 {len(collected_urls)} 篇新文章 URL")
    return collected_urls


# ============================================================
# 第八步：排程自動執行
# ============================================================

def run_scheduled(args):
    """排程模式：定期自動執行爬蟲任務"""
    try:
        import schedule
    except ImportError:
        logger.error("排程模式需要 schedule 套件：pip install schedule")
        sys.exit(1)

    def job():
        logger.info("[排程] 開始執行定時任務...")
        if args.ptt_board:
            urls = fetch_ptt_board(args.ptt_board, args.pages, args.output)
            if urls:
                batch_fetch_urls(urls, args.output)
            else:
                logger.info("[排程] 沒有新文章")
        elif args.batch:
            batch_fetch(args.batch, args.output)
        else:
            logger.warning("[排程] 排程模式需搭配 --ptt-board 或 --batch 使用")
            return
        logger.info("[排程] 任務完成，等待下次執行...")

    interval = args.schedule
    schedule.every(interval).minutes.do(job)

    logger.info(f"[排程] 已啟動，每 {interval} 分鐘執行一次（Ctrl+C 停止）")
    job()  # 立即執行第一次

    try:
        while True:
            schedule.run_pending()
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("[排程] 已停止")


# ============================================================
# CLI 入口
# ============================================================

def main():
    global _CONFIG, DEFAULT_OUTPUT_DIR, REQUEST_TIMEOUT, MAX_RETRIES
    global RETRY_BASE_DELAY, POLITENESS_DELAY, JINA_BASE_URL

    parser = argparse.ArgumentParser(
        description="🐾 獸醫文章自動化擷取工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  # 擷取單篇文章
  python scraper.py https://www.ptt.cc/bbs/dog/M.xxxxx.html

  # 批次擷取（從檔案讀取 URL）
  python scraper.py --batch urls.txt

  # 指定輸出目錄
  python scraper.py https://example.com --output ~/obsidian/vet-articles

  # 只識別平台（不擷取）
  python scraper.py https://facebook.com/some-post --identify

  # PTT 看板自動爬取（最新 3 頁）
  python scraper.py --ptt-board cat --pages 3

  # 排程模式（每 60 分鐘自動執行）
  python scraper.py --ptt-board cat --pages 2 --schedule 60
        """
    )
    parser.add_argument("url", nargs="?", help="要擷取的網頁 URL")
    parser.add_argument("--batch", "-b", help="批次模式：URL 列表檔案路徑")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT_DIR,
                        help=f"輸出目錄（預設：{DEFAULT_OUTPUT_DIR}）")
    parser.add_argument("--identify", "-i", action="store_true",
                        help="只識別平台，不擷取內容")
    parser.add_argument("--config", "-c", default=None,
                        help="設定檔路徑（預設：同目錄下的 config.json）")
    parser.add_argument("--ptt-board", help="PTT 看板名稱（自動爬取文章列表）")
    parser.add_argument("--pages", type=int, default=1,
                        help="PTT 看板頁數（預設：1）")
    parser.add_argument("--schedule", type=int, metavar="MINUTES",
                        help="排程模式：每隔 N 分鐘自動執行")

    args = parser.parse_args()

    # 重新載入設定（如有指定 --config）
    if args.config:
        _CONFIG = load_config(args.config)
        DEFAULT_OUTPUT_DIR = _CONFIG["output_dir"]
        REQUEST_TIMEOUT = _CONFIG["request_timeout"]
        MAX_RETRIES = _CONFIG["max_retries"]
        RETRY_BASE_DELAY = _CONFIG["retry_base_delay"]
        POLITENESS_DELAY = _CONFIG["politeness_delay"]
        JINA_BASE_URL = _CONFIG["jina_base_url"]
        if args.output == os.path.expanduser("~/vet-articles"):
            args.output = DEFAULT_OUTPUT_DIR

    # 初始化日誌（console + file）
    _setup_logging(log_dir=args.output, level=_CONFIG.get("log_level", "INFO"))

    if not args.url and not args.batch and not args.ptt_board:
        parser.print_help()
        sys.exit(1)

    # 純識別模式
    if args.identify and args.url:
        info = identify_platform(args.url)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return

    # 排程模式
    if args.schedule:
        run_scheduled(args)
        return

    # PTT 看板模式
    if args.ptt_board:
        urls = fetch_ptt_board(args.ptt_board, args.pages, args.output)
        if urls:
            batch_fetch_urls(urls, args.output)
        else:
            logger.info("沒有新文章需要擷取")
        return

    # 批次模式
    if args.batch:
        batch_fetch(args.batch, args.output)
        return

    # 單一 URL 模式
    if args.url:
        if is_already_fetched(args.url, args.output):
            logger.info(f"此 URL 已下載過：{args.url}")
            logger.info("如要重新下載，請刪除輸出目錄中的 .fetched_urls.json 對應記錄")
            return
        article = fetch_article(args.url)
        if article:
            save_path = save_article(article, args.output)
            mark_as_fetched(args.url, args.output)
            logger.info(f"文章已儲存到：{save_path}")
        else:
            logger.error(f"擷取失敗：{args.url}")
            sys.exit(1)


if __name__ == "__main__":
    main()
