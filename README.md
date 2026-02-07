# 🐾 獸醫文章自動化擷取工具

一鍵擷取網路上的獸醫文章，自動轉成 Markdown 並下載圖片到本地，方便匯入 Obsidian 建立知識庫。

## 快速開始

### 安裝

```bash
pip install requests beautifulsoup4 markdownify
```

### 基本用法

```bash
# 擷取單篇文章
python scraper.py https://www.ptt.cc/bbs/dog/M.xxxxx.html

# 批次擷取（從檔案讀取 URL 列表）
python scraper.py --batch urls.txt

# 指定輸出目錄（例如 Obsidian vault）
python scraper.py https://example.com --output ~/obsidian-vault/vet-articles

# 只識別平台，不擷取
python scraper.py https://facebook.com/xxx --identify
```

### 輸出結構

```
~/vet-articles/
├── 2026-02-07_某篇獸醫文章標題/
│   ├── content.md          # 文章內容（Markdown）
│   ├── metadata.json       # 元資料（標題、來源、時間）
│   └── images/
│       ├── img_01.jpg
│       └── img_02.png
├── 2026-02-07_另一篇文章/
│   └── ...
└── batch_report_20260207_143000.json  # 批次報告
```

## 擷取策略

| 策略 | 說明 | 成本 | 適合場景 |
|------|------|------|----------|
| Jina Reader | 免費 API，自動轉 Markdown | 免費 | 大多數公開網站 |
| BeautifulSoup | 直接解析 HTML | 免費 | 簡單結構的網站 |
| *(未來)* Playwright | 瀏覽器自動化 | 免費 | 需要 JS 渲染的頁面 |

### 支援平台

| 平台 | 支援狀態 | 策略 |
|------|----------|------|
| PTT | ✅ 完全支援 | Jina → BS4 |
| Medium | ✅ 完全支援 | Jina → BS4 |
| 新聞網站 (UDN, ETtoday, LTN...) | ✅ 完全支援 | Jina → BS4 |
| 痞客邦、方格子 | ✅ 完全支援 | Jina → BS4 |
| LINE TODAY | ✅ 完全支援 | Jina → BS4 |
| 獸醫學會網站 | ✅ 支援 | BS4 → Jina |
| Facebook | ⏭️ 跳過 | 請用 Chrome Extension |
| Instagram | ⏭️ 跳過 | 請用 Chrome Extension |

## 搭配 Obsidian

1. 設定 `--output` 到你的 Obsidian vault 目錄
2. 或者在 Obsidian 中把 `~/vet-articles` 加入為 vault

```bash
# 直接輸出到 Obsidian
python scraper.py --batch urls.txt --output ~/my-obsidian-vault/獸醫文章
```

## 批次模式

編輯 `urls.txt`，每行放一個 URL：

```
# 可用 # 寫註解
https://www.ptt.cc/bbs/dog/M.xxxxx.html
https://medium.com/@author/article
https://udn.com/news/story/xxxxx
```

然後執行：

```bash
python scraper.py --batch urls.txt
```

完成後會產生 `batch_report_*.json` 統計成功/失敗/跳過的數量。

## 後續擴充

此工具是三模組系統的第一部分：

- **模組一**（本工具）：自動化爬蟲，處理好爬的平台
- **模組二**：Chrome Extension，一鍵儲存 Facebook/IG 貼文
- **模組三**：批次整理腳本，用 AI 分類摘要已收集的內容
