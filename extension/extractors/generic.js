/**
 * CLIMB Extension — Generic Extractor (generic.js)
 * =================================================
 * 通用頁面提取器，適用於大部分網站。
 * 嘗試找到主要內容區域，移除導覽、廣告等非內容元素。
 */

/**
 * 提取頁面的主要內容
 */
function extractGeneric() {
  const title = document.title || "Untitled";
  const url = window.location.href;

  // 找到主要內容區域
  const contentEl = findMainContent();
  if (!contentEl) {
    return {
      title: title,
      content: document.body.innerText.substring(0, 5000),
      url: url,
      platform: "其他",
      source: "chrome-ext",
      images: [],
    };
  }

  // 複製節點，避免修改原始 DOM
  const clone = contentEl.cloneNode(true);

  // 移除非內容元素
  const removeSelectors = [
    "script", "style", "noscript", "iframe",
    "nav", "header", "footer", "aside",
    ".sidebar", ".menu", ".nav", ".navigation",
    ".advertisement", ".ad", ".ads",
    ".social-share", ".share-buttons",
    ".comments", ".comment-section",
    ".related-posts", ".recommended",
  ];

  removeSelectors.forEach((sel) => {
    clone.querySelectorAll(sel).forEach((el) => el.remove());
  });

  // 提取文字內容
  const content = clone.innerText.trim();

  // 提取圖片
  const images = extractImages(contentEl);

  return {
    title: title,
    content: content,
    url: url,
    platform: "其他",
    source: "chrome-ext",
    images: images,
  };
}

/**
 * 找到頁面的主要內容區域
 * 依優先順序嘗試多個選擇器
 */
function findMainContent() {
  const selectors = [
    "article",
    '[role="article"]',
    "main",
    ".post-content",
    ".entry-content",
    ".article-content",
    ".article-body",
    ".post-body",
    ".content-body",
    "#content",
    ".content",
    "#main-content",
    ".main-content",
  ];

  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim().length > 100) {
      return el;
    }
  }

  // 最後手段：使用 body
  return document.body;
}

/**
 * 從內容區域提取圖片 URL
 * 過濾掉太小的圖片（圖示、按鈕等）
 */
function extractImages(container) {
  const images = [];
  const seen = new Set();

  container.querySelectorAll("img").forEach((img) => {
    const src = img.src || img.getAttribute("data-src") || "";
    if (!src || src.startsWith("data:")) return;

    // 過濾太小的圖片（可能是圖示或 UI 元素）
    const width = img.naturalWidth || img.width || 0;
    const height = img.naturalHeight || img.height || 0;
    if (width > 0 && width < 80) return;
    if (height > 0 && height < 80) return;

    // 去重
    if (seen.has(src)) return;
    seen.add(src);

    images.push(src);
  });

  return images;
}
