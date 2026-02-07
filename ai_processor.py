"""
AI 批次處理模組
================
使用 Claude API 對已擷取的文章進行分類、摘要、關鍵資訊提取。

用法（CLI）：
  # 掃描並列出文章
  python ai_processor.py --scan ~/vet-articles

  # 處理所有未處理的文章
  python ai_processor.py --process ~/vet-articles

  # 強制重新處理所有文章
  python ai_processor.py --process ~/vet-articles --force
"""

import json
import os
import re
import sys
import logging
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# 獸醫專業分類體系
# ============================================================

VET_CATEGORIES = {
    "內科": ["腎臟", "心臟", "內分泌", "腫瘤", "感染症", "消化", "呼吸", "神經"],
    "外科": ["骨科", "軟組織", "眼科", "牙科"],
    "急診與重症": [],
    "影像診斷": [],
    "臨床病理": [],
    "營養學": [],
    "行為學": [],
    "公共衛生": [],
    "藥理學": [],
    "其他": [],
}

# 所有子類別的展平列表（用於 prompt）
ALL_SUBCATEGORIES = []
for cat, subs in VET_CATEGORIES.items():
    if subs:
        for sub in subs:
            ALL_SUBCATEGORIES.append(f"{cat}/{sub}")
    else:
        ALL_SUBCATEGORIES.append(cat)

# ============================================================
# 設定
# ============================================================

DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_MAX_TOKENS = 2000
DEFAULT_API_DELAY = 1.0  # 每次 API 呼叫之間的間隔（秒）
MAX_ARTICLE_CHARS = 8000  # 超過此長度的文章會被截斷

# ============================================================
# Anthropic SDK（選用）
# ============================================================

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


# ============================================================
# Frontmatter 解析和更新
# ============================================================

_FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 YAML frontmatter。

    Args:
        content: 完整的 Markdown 內容

    Returns:
        (frontmatter_dict, body_content) — frontmatter 字典和正文
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    fm_block = match.group(1)
    body = content[match.end():]
    fm = {}

    for line in fm_block.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # 解析 key: value
        colon_idx = line.find(':')
        if colon_idx < 0:
            continue
        key = line[:colon_idx].strip()
        value = line[colon_idx + 1:].strip()

        # 解析值
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        elif value == '[]':
            value = []
        elif value.startswith('[') and value.endswith(']'):
            # 簡單列表解析
            inner = value[1:-1]
            value = [v.strip().strip('"').strip("'") for v in inner.split(',') if v.strip()]
        elif value == '""' or value == "''":
            value = ""

        fm[key] = value

    return fm, body


def update_frontmatter(content: str, updates: dict) -> str:
    """更新 frontmatter 欄位，保留其他欄位不變。

    Args:
        content: 完整的 Markdown 內容
        updates: 要更新/新增的欄位

    Returns:
        更新後的完整 Markdown 內容
    """
    fm, body = parse_frontmatter(content)
    fm.update(updates)

    # 重建 frontmatter
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                items = ', '.join(f'"{v}"' if isinstance(v, str) else str(v)
                                 for v in value)
                lines.append(f"{key}: [{items}]")
        elif isinstance(value, str):
            # 需要引號的情況
            if ':' in value or '"' in value or value.startswith('['):
                safe = value.replace('"', '\\"')
                lines.append(f'{key}: "{safe}"')
            else:
                lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")

    return '\n'.join(lines) + body


# ============================================================
# 文章掃描
# ============================================================

def scan_articles(output_dir: str) -> list[dict]:
    """掃描輸出目錄中的文章。

    Args:
        output_dir: 文章輸出目錄路徑

    Returns:
        文章列表，每篇包含 path, title, platform, has_ai_data, char_count
    """
    output_dir = os.path.expanduser(output_dir)
    articles = []

    if not os.path.isdir(output_dir):
        logger.warning(f"目錄不存在：{output_dir}")
        return articles

    for entry in sorted(os.listdir(output_dir)):
        entry_path = os.path.join(output_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        content_path = os.path.join(entry_path, "content.md")
        if not os.path.isfile(content_path):
            continue

        try:
            with open(content_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (IOError, UnicodeDecodeError) as e:
            logger.warning(f"無法讀取 {content_path}：{e}")
            continue

        fm, body = parse_frontmatter(content)

        # 判斷是否已有 AI 處理資料
        has_ai_data = bool(fm.get("category")) and bool(fm.get("summary"))

        # 讀取 metadata.json 以獲取更多資訊
        meta_path = os.path.join(entry_path, "metadata.json")
        platform = fm.get("platform", "")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                platform = platform or meta.get("platform", "")
            except (json.JSONDecodeError, IOError):
                pass

        articles.append({
            "path": entry_path,
            "title": fm.get("title", entry),
            "platform": platform,
            "has_ai_data": has_ai_data,
            "char_count": len(body),
        })

    return articles


def estimate_cost(articles: list[dict], model: str = DEFAULT_MODEL) -> dict:
    """估算 AI 處理費用。

    Args:
        articles: 文章列表（來自 scan_articles）
        model: 使用的模型名稱

    Returns:
        包含 article_count, total_chars, estimated_input_tokens,
        estimated_output_tokens, estimated_cost_usd, model 的字典
    """
    unprocessed = [a for a in articles if not a.get("has_ai_data")]
    total_chars = sum(min(a["char_count"], MAX_ARTICLE_CHARS) for a in unprocessed)

    # 中文字元 token 密度較高（約 1.5-2 token/char），加上 system prompt
    system_prompt_tokens = 500  # 系統提示大約 500 token
    estimated_input_tokens = int(total_chars / 2.5) + system_prompt_tokens * len(unprocessed)
    estimated_output_tokens = 300 * len(unprocessed)  # 每篇回傳約 300 token

    # 定價（以 Sonnet 為基準）
    # Input: $3/M tokens, Output: $15/M tokens
    if "sonnet" in model.lower():
        input_cost_per_m = 3.0
        output_cost_per_m = 15.0
    elif "haiku" in model.lower():
        input_cost_per_m = 0.25
        output_cost_per_m = 1.25
    elif "opus" in model.lower():
        input_cost_per_m = 15.0
        output_cost_per_m = 75.0
    else:
        input_cost_per_m = 3.0
        output_cost_per_m = 15.0

    cost = (estimated_input_tokens * input_cost_per_m +
            estimated_output_tokens * output_cost_per_m) / 1_000_000

    return {
        "article_count": len(unprocessed),
        "total_articles": len(articles),
        "total_chars": total_chars,
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_output_tokens": estimated_output_tokens,
        "estimated_cost_usd": round(cost, 4),
        "model": model,
    }


# ============================================================
# Claude API 互動
# ============================================================

SYSTEM_PROMPT = """你是一位資深獸醫師和醫學文獻分析專家。請分析以下獸醫相關文章，並提供結構化的分類和摘要。

## 分類體系

請從以下類別中選擇最合適的：

- 內科：腎臟 / 心臟 / 內分泌 / 腫瘤 / 感染症 / 消化 / 呼吸 / 神經
- 外科：骨科 / 軟組織 / 眼科 / 牙科
- 急診與重症
- 影像診斷
- 臨床病理
- 營養學
- 行為學
- 公共衛生
- 藥理學
- 其他

## 回傳格式

請以 JSON 格式回傳，結構如下：
```json
{
  "category": "主類別",
  "subcategory": "子類別（如果有的話，否則為空字串）",
  "tags": ["標籤1", "標籤2", "標籤3"],
  "summary": "50-150 字的一段話摘要",
  "key_points": ["臨床重點1", "臨床重點2", "臨床重點3"],
  "clinical_relevance": "一句話說明對臨床實務的意義"
}
```

## 注意事項

- 標籤請使用中文，3-8 個
- 摘要控制在 50-150 字
- 關鍵要點 3-5 個
- 如果文章非獸醫相關，category 設為 "其他"
- 只回傳 JSON，不要加其他說明文字"""


def _build_user_prompt(article_text: str, title: str = "") -> str:
    """建構使用者端的 prompt。"""
    header = f"文章標題：{title}\n\n" if title else ""
    # 截斷過長的文章
    if len(article_text) > MAX_ARTICLE_CHARS:
        article_text = article_text[:MAX_ARTICLE_CHARS] + "\n\n[... 文章已截斷 ...]"
    return f"{header}以下是文章內容：\n\n{article_text}"


def process_single_article(
    article_text: str,
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    title: str = "",
) -> dict:
    """用 Claude API 處理單篇文章。

    Args:
        article_text: 文章正文
        api_key: Anthropic API Key
        model: 模型名稱
        max_tokens: 最大回傳 token 數
        title: 文章標題（可選，增加上下文）

    Returns:
        包含 category, subcategory, tags, summary, key_points, clinical_relevance 的字典

    Raises:
        ImportError: 未安裝 anthropic
        RuntimeError: API 呼叫或回應解析失敗
    """
    if not HAS_ANTHROPIC:
        raise ImportError(
            "anthropic 套件未安裝，請執行 pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)

    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": _build_user_prompt(article_text, title),
            }],
        )
    except anthropic.APIError as e:
        raise RuntimeError(f"Claude API 錯誤：{e}") from e

    # 解析回應
    response_text = message.content[0].text.strip()

    # 嘗試直接解析 JSON
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        # 嘗試從 markdown code block 中提取 JSON
        json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', response_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"無法解析 Claude 回應為 JSON：{response_text[:200]}"
                )
        else:
            raise RuntimeError(
                f"無法解析 Claude 回應為 JSON：{response_text[:200]}"
            )

    # 驗證必要欄位
    required_keys = {"category", "tags", "summary"}
    missing = required_keys - set(result.keys())
    if missing:
        raise RuntimeError(f"Claude 回應缺少欄位：{missing}")

    # 正規化
    result.setdefault("subcategory", "")
    result.setdefault("key_points", [])
    result.setdefault("clinical_relevance", "")

    # 確保 tags 是列表
    if isinstance(result["tags"], str):
        result["tags"] = [t.strip() for t in result["tags"].split(",")]

    return result


def process_article_batch(
    articles: list[dict],
    api_key: str,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    api_delay: float = DEFAULT_API_DELAY,
    on_progress: Optional[callable] = None,
    cancel_event=None,
) -> dict:
    """批次處理多篇文章。

    Args:
        articles: 文章列表（來自 scan_articles，每篇需含 path）
        api_key: Anthropic API Key
        model: 模型名稱
        max_tokens: 最大回傳 token 數
        api_delay: API 呼叫間隔（秒）
        on_progress: 進度回調 (current, total, message)
        cancel_event: threading.Event，設定時取消處理

    Returns:
        {"success": int, "failed": int, "results": list[dict]}
    """
    total = len(articles)
    success_count = 0
    failed_count = 0
    results = []

    for i, article in enumerate(articles, 1):
        if cancel_event and cancel_event.is_set():
            logger.info("AI 處理已被使用者取消")
            break

        title = article.get("title", "未知")
        path = article.get("path", "")

        if on_progress:
            on_progress(i, total, f"正在處理：{title}")

        try:
            # 讀取文章內容
            content_path = os.path.join(path, "content.md")
            with open(content_path, "r", encoding="utf-8") as f:
                content = f.read()

            fm, body = parse_frontmatter(content)

            # 呼叫 Claude API
            ai_result = process_single_article(
                body, api_key, model, max_tokens, title=title,
            )

            # 更新 frontmatter
            fm_updates = {
                "category": (f"{ai_result['category']}/{ai_result['subcategory']}"
                             if ai_result.get("subcategory")
                             else ai_result["category"]),
                "tags": ai_result.get("tags", []),
                "summary": ai_result.get("summary", ""),
                "key_points": ai_result.get("key_points", []),
                "clinical_relevance": ai_result.get("clinical_relevance", ""),
            }
            updated_content = update_frontmatter(content, fm_updates)

            with open(content_path, "w", encoding="utf-8") as f:
                f.write(updated_content)

            # 更新 metadata.json
            meta_path = os.path.join(path, "metadata.json")
            if os.path.isfile(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except (json.JSONDecodeError, IOError):
                    meta = {}
            else:
                meta = {}

            meta.update({
                "category": fm_updates["category"],
                "tags": ai_result.get("tags", []),
                "summary": ai_result.get("summary", ""),
                "ai_model": model,
                "ai_processed_at": datetime.now().isoformat(),
            })

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
                f.write("\n")

            results.append({
                "title": title,
                "status": "success",
                "category": fm_updates["category"],
                "path": path,
            })
            success_count += 1
            logger.info(f"[AI] ✅ {title} → {fm_updates['category']}")

        except Exception as e:
            logger.error(f"[AI] ❌ {title}：{e}")
            results.append({
                "title": title,
                "status": "failed",
                "error": str(e),
                "path": path,
            })
            failed_count += 1

        # API 呼叫間隔
        if i < total and not (cancel_event and cancel_event.is_set()):
            time.sleep(api_delay)

    if on_progress:
        on_progress(total, total, "AI 處理完成")

    return {
        "success": success_count,
        "failed": failed_count,
        "results": results,
    }


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI 文章批次處理工具")
    parser.add_argument("--scan", metavar="DIR", help="掃描文章目錄")
    parser.add_argument("--process", metavar="DIR", help="處理文章目錄")
    parser.add_argument("--force", action="store_true", help="強制重新處理所有文章")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Claude 模型名稱")
    parser.add_argument("--delay", type=float, default=DEFAULT_API_DELAY,
                        help="API 呼叫間隔（秒）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.scan:
        articles = scan_articles(args.scan)
        print(f"\n找到 {len(articles)} 篇文章：")
        for a in articles:
            status = "✅ 已處理" if a["has_ai_data"] else "⬜ 未處理"
            print(f"  {status} | {a['platform']:12s} | {a['title']}")

        cost = estimate_cost(articles, args.model)
        print(f"\n未處理：{cost['article_count']} 篇")
        print(f"預估費用：~${cost['estimated_cost_usd']:.4f} USD ({cost['model']})")

    elif args.process:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            print("錯誤：請設定 ANTHROPIC_API_KEY 環境變數")
            sys.exit(1)

        articles = scan_articles(args.process)
        if not args.force:
            articles = [a for a in articles if not a["has_ai_data"]]

        if not articles:
            print("沒有需要處理的文章")
            return

        print(f"即將處理 {len(articles)} 篇文章...")
        cost = estimate_cost(
            [{"char_count": a["char_count"], "has_ai_data": False} for a in articles],
            args.model,
        )
        print(f"預估費用：~${cost['estimated_cost_usd']:.4f} USD")

        def progress_cb(current, total, msg):
            print(f"  [{current}/{total}] {msg}")

        result = process_article_batch(
            articles, api_key, model=args.model,
            api_delay=args.delay, on_progress=progress_cb,
        )
        print(f"\n完成！成功：{result['success']}，失敗：{result['failed']}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
