# 獸醫社群內容擷取與整理系統

## 專案目標

建立一套自動化工具，從台灣獸醫社群（Facebook 粉專、PTT、Medium、新聞網站等）高效收集專業討論內容，整理消化後產出衛教文章，供上弦動物生技公司的平台使用。

## 使用者背景

- 使用者是獸醫師兼創業者，經營「上弦動物生技公司」
- 正在開發 shangxian-platform（獸醫醫療服務平台，含飼主端、診所端、電商）
- 使用 Next.js + Supabase 技術棧
- 需要高效收集獸醫社群的專業討論風向，無時間逐則瀏覽
- 最終目標：收集 → 整理 → 產出衛教文章 → 發佈到平台

## 系統架構

三個模組各自負責不同場景，最終匯入統一的知識庫：

```
模組一：自動化爬蟲（好爬平台）──┐
模組二：Chrome Extension（FB/IG）──┼──→ 統一 Markdown 知識庫 ──→ AI 摘要/衛教文章
模組三：批次整理腳本（已存貼文）──┘
```

### 統一輸出格式

所有模組產出的文章都遵循相同結構：

```
~/vet-articles/
├── YYYY-MM-DD_文章標題/
│   ├── content.md          # 文章內容（含 YAML frontmatter）
│   ├── metadata.json       # 結構化元資料
│   └── images/
│       ├── img_01.jpg
│       └── img_02.png
└── batch_report_*.json     # 批次擷取報告
```

content.md 的 frontmatter 格式：

```yaml
---
title: "文章標題"
source: https://原始URL
platform: PTT | Medium | Facebook | ...
fetched_by: jina | bs4 | playwright | chrome-ext | manual
date: YYYY-MM-DD HH:MM:SS
tags: []           # 未來由 AI 自動標註
category: ""       # 未來由 AI 自動分類
summary: ""        # 未來由 AI 自動摘要
---
```

---

## 模組一：自動化爬蟲（✅ 已完成基礎版）

### 現有檔案

- `scraper.py` — 主程式，含平台識別、Jina/BS4 雙策略降級、圖片下載、Markdown 儲存
- `urls.txt` — 批次 URL 清單範本
- `README.md` — 使用說明

### 擷取策略

| 優先順序 | 策略 | 說明 | 狀態 |
|---------|------|------|------|
| 1 | Jina Reader | 免費 API，`r.jina.ai/{url}` 自動轉 Markdown | ✅ 已實作 |
| 2 | BeautifulSoup | requests + BS4 直接解析 HTML | ✅ 已實作 |
| 3 | Playwright | 瀏覽器自動化，處理 JS 渲染頁面 | ❌ 待實作 |

### 平台支援

| 平台 | 策略 | 狀態 |
|------|------|------|
| PTT | Jina → BS4 | ✅ |
| Medium | Jina → BS4 | ✅ |
| 新聞網站 (UDN, ETtoday, LTN, CNA, TVBS, 中時, 三立) | Jina → BS4 | ✅ |
| 痞客邦、方格子、LINE TODAY | Jina → BS4 | ✅ |
| 獸醫學會網站 | BS4 → Jina | ✅ |
| Facebook / Instagram | 自動跳過，提醒用 Chrome Extension | ✅（設計如此）|

### 待開發功能

- [ ] Playwright 第三層策略（處理需要 JS 渲染的頁面）
- [ ] 排程自動執行（cron 或 schedule 套件）
- [ ] 重複 URL 偵測（避免重抓同一篇）
- [ ] 抓取失敗的自動重試機制
- [ ] 支援抓取 PTT 看板列表頁，自動提取文章 URL

### CLI 使用方式

```bash
# 安裝依賴
pip install requests beautifulsoup4 markdownify

# 單篇擷取
python scraper.py https://www.ptt.cc/bbs/dog/M.xxxxx.html

# 批次擷取
python scraper.py --batch urls.txt

# 指定輸出到 Obsidian
python scraper.py --batch urls.txt --output ~/obsidian-vault/獸醫文章

# 識別平台
python scraper.py https://facebook.com/xxx --identify
```

### 關鍵技術細節

- Jina Reader：在 URL 前加 `https://r.jina.ai/`，設定 `Accept: text/markdown`
- 圖片下載：需根據平台設定不同 Referer header（如小紅書需要 `Referer: https://www.xiaohongshu.com/`）
- 編碼處理：使用 `resp.apparent_encoding` 自動偵測
- 內容驗證：長度 < 100 字元視為擷取失敗
- 禮貌延遲：批次模式每次間隔 2 秒

---

## 模組二：Chrome Extension（❌ 待開發）

### 目的

解決 Facebook 粉專/社團、Instagram 等需要登入且反爬嚴格的平台。使用者正常瀏覽時，按一下按鈕即可儲存當前貼文。

### 設計規格

**核心功能：**
- 瀏覽器工具列按鈕，一鍵儲存當前頁面/貼文
- 自動擷取貼文文字內容、圖片、作者、時間
- 儲存為與模組一相同的 Markdown 格式
- 支援 Facebook 粉專貼文、社團貼文、Instagram 貼文

**技術方案：**
- Manifest V3 Chrome Extension
- Content Script 注入頁面擷取 DOM
- 使用 `chrome.downloads` API 儲存檔案到本地
- 或使用 `fetch` 送到本地 API server 儲存

**Facebook 貼文擷取邏輯：**
- 貼文容器：`div[data-ad-preview]` 或 `div[role="article"]`
- 文字內容：`div[data-ad-comet-above-more-info]` 或展開後的文字區塊
- 圖片：`img` 標籤的 `src` 屬性
- 作者：貼文頂部的連結文字
- 時間：`abbr` 標籤或 `aria-label` 含時間的元素

**注意：Facebook DOM 結構經常變動，需要彈性的選擇器策略。**

**儲存方式（兩種方案擇一）：**

方案 A — 純本地：
```
Extension → chrome.downloads API → ~/vet-articles/YYYY-MM-DD_標題/
```

方案 B — 搭配本地 server：
```
Extension → POST http://localhost:3456/save → Python server → ~/vet-articles/
```

方案 B 更靈活，可以復用模組一的儲存邏輯。

### 待確認

- [ ] 選擇方案 A 或 B
- [ ] 是否需要支援批次選取多則貼文
- [ ] 是否需要 popup UI 顯示已儲存的文章列表
- [ ] 是否要同步到 Supabase（配合 shangxian-platform）

---

## 模組三：批次整理腳本（❌ 待開發）

### 目的

處理使用者已經手動儲存的大量貼文（截圖、複製的文字、書籤、筆記等），用 Claude API 批次進行分類、摘要、知識提取。

### 設計規格

**輸入格式支援：**
- 純文字檔（.txt）— 複製貼上的貼文
- Markdown 檔（.md）— 已整理的筆記
- 圖片（.jpg, .png）— 貼文截圖，需 OCR
- JSON — 模組一/二的 metadata 輸出
- 混合目錄 — 自動偵測檔案類型

**AI 處理 Pipeline：**

```
輸入檔案 → 檔案類型偵測 → 內容提取 → Claude API 批次處理 → 輸出
                                              │
                                    ┌─────────┼─────────┐
                                    ▼         ▼         ▼
                                  分類      摘要     關鍵資訊
```

**分類體系（獸醫專業）：**
- 內科：腎臟、心臟、內分泌、腫瘤、感染症、消化、呼吸、神經
- 外科：骨科、軟組織、眼科、牙科
- 急診與重症
- 影像診斷
- 臨床病理 / 實驗室
- 營養學
- 行為學
- 公共衛生 / 法規
- 藥理學
- 其他

**輸出格式：**

```yaml
---
title: "原始標題或 AI 生成標題"
source: 原始來源
platform: 平台
category: 內科/腎臟        # AI 分類
tags: [CKD, SDMA, 貓, 老年]  # AI 標籤
summary: "一段話摘要"       # AI 摘要
key_points:                 # AI 提取的關鍵資訊
  - point1
  - point2
clinical_relevance: "臨床意義"  # AI 評估
date_processed: YYYY-MM-DD
---

（原始內容）
```

### Claude API 使用

```python
# 使用 Anthropic Python SDK
# model: claude-sonnet-4-20250514（性價比最佳）
# 批次處理建議使用 Message Batches API 降低成本

import anthropic
client = anthropic.Anthropic()  # 從環境變數讀取 ANTHROPIC_API_KEY
```

**Prompt 策略：**
- System prompt 設定獸醫專業背景
- 要求 JSON 格式輸出，方便程式解析
- 每次送入一篇文章，避免 context 過長
- 對截圖使用 vision 能力進行 OCR

### 待確認

- [ ] Claude API key 是否已準備好
- [ ] 優先處理哪種輸入格式
- [ ] 分類體系是否需要調整
- [ ] 是否需要產出衛教文章草稿（還是先做到分類摘要即可）

---

## 技術棧

| 工具 | 用途 |
|------|------|
| Python 3.10+ | 模組一、模組三主要語言 |
| requests | HTTP 請求 |
| BeautifulSoup4 | HTML 解析 |
| markdownify | HTML → Markdown 轉換 |
| Playwright (待裝) | 瀏覽器自動化兜底策略 |
| Jina Reader API | 免費網頁轉 Markdown |
| Chrome Extension (Manifest V3) | 模組二，JS/HTML/CSS |
| Anthropic Claude API | 模組三 AI 處理 |
| Obsidian | 知識庫瀏覽與管理 |

### 未來可整合

- Supabase：將文章元資料存入 shangxian-platform 的資料庫
- RAG 系統：與現有的獸醫知識庫 RAG 整合
- 自動發佈：整理好的衛教文章自動推送到平台

---

## 開發優先順序

1. ✅ 模組一基礎版（已完成）
2. 🔜 模組二 Chrome Extension（解決 Facebook 粉專這個最大痛點）
3. 🔜 模組三批次整理腳本（處理已儲存的內容）
4. 模組一增強：加入 Playwright、排程、重複偵測
5. AI Pipeline：自動分類 + 摘要 + 衛教文章草稿生成
6. 平台整合：接入 Supabase 和 shangxian-platform

---

## 注意事項

- Facebook 爬蟲有違反 ToS 的風險，因此選擇 Chrome Extension 方案（使用者主動操作儲存）
- 圖片下載需根據不同平台設定 Referer header
- 批次爬取應設禮貌延遲（≥2 秒），避免被封 IP
- Claude API 費用：Sonnet 模型約 $3/百萬 input tokens，批次處理可用 Batches API 減半
- 所有產出以 Markdown 為核心格式，確保 Obsidian 相容性
