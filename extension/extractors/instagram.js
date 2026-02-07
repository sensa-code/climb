/**
 * CLIMB Extension — Instagram Extractor (instagram.js)
 * =====================================================
 * Instagram 專用的貼文內容提取器。
 * 支援單圖、多圖 Carousel、Reels 頁面。
 */

/**
 * 提取 Instagram 貼文內容
 */
function extractInstagram() {
  // 找到貼文容器
  const post = findIGPostContainer();
  if (!post) {
    return null;
  }

  // 提取各部分
  const author = extractIGAuthor(post);
  const caption = extractIGCaption(post);
  const images = extractIGImages(post);
  const timestamp = extractIGTimestamp(post);

  if (!caption && images.length === 0) {
    return null;
  }

  // 組裝 Markdown 內容
  let markdown = "";
  if (author) {
    markdown += `**@${author}**\n\n`;
  }
  if (timestamp) {
    markdown += `> ${timestamp}\n\n`;
  }
  if (caption) {
    markdown += caption;
  }

  const title = author
    ? `${author} - Instagram 貼文`
    : "Instagram 貼文";

  return {
    title: title,
    content: markdown,
    url: window.location.href,
    platform: "Instagram",
    source: "chrome-ext",
    images: images,
  };
}

/**
 * 找到 Instagram 貼文容器
 */
function findIGPostContainer() {
  const selectors = [
    "article",
    '[role="presentation"]',
    "main",
  ];

  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el) return el;
  }

  return null;
}

/**
 * 提取作者用戶名
 */
function extractIGAuthor(post) {
  // 貼文頁面通常在 header 有作者連結
  const authorSelectors = [
    "header a",
    'a[role="link"]',
  ];

  for (const sel of authorSelectors) {
    const links = post.querySelectorAll(sel);
    for (const link of links) {
      const href = link.getAttribute("href") || "";
      // Instagram 用戶頁面格式：/username/
      const match = href.match(/^\/([a-zA-Z0-9_.]+)\/?$/);
      if (match && match[1] !== "explore" && match[1] !== "p") {
        return match[1];
      }
    }
  }

  // 備選：從 URL 提取（如果是 /username/p/xxx/ 格式）
  const urlMatch = window.location.pathname.match(/^\/([a-zA-Z0-9_.]+)\/(?:p|reel)\//);
  if (urlMatch) {
    return urlMatch[1];
  }

  return null;
}

/**
 * 提取貼文說明文字（Caption）
 */
function extractIGCaption(post) {
  // Instagram 的說明文字通常在特定容器中
  const captionSelectors = [
    'h1',                        // 新版 IG 有時用 h1
    'div[role="button"] span',   // 展開的說明文字
    'span[dir="auto"]',          // 文字方向標記的 span
    'li span',                   // 在留言列表中的第一則（通常是說明文字）
  ];

  // 先嘗試展開「更多」按鈕
  post.querySelectorAll('[role="button"]').forEach((btn) => {
    const text = btn.textContent.trim();
    if (text === "more" || text === "更多" || text === "...more") {
      try { btn.click(); } catch (e) { /* ignore */ }
    }
  });

  // 收集所有可能的說明文字
  let bestCaption = "";

  for (const sel of captionSelectors) {
    const elements = post.querySelectorAll(sel);
    for (const el of elements) {
      const text = el.innerText.trim();
      // 說明文字通常較長，過濾掉太短的（如按鈕文字）
      if (text.length > bestCaption.length && text.length > 20) {
        // 排除明顯的 UI 文字
        if (!isUIText(text)) {
          bestCaption = text;
        }
      }
    }
  }

  return bestCaption;
}

/**
 * 判斷是否為 UI 文字（非貼文內容）
 */
function isUIText(text) {
  const uiPatterns = [
    /^(Like|Comment|Share|Save|More)$/i,
    /^(讚|留言|分享|儲存|更多)$/,
    /^\d+\s*(likes?|comments?|views?)$/i,
    /^\d+\s*(個讚|則留言|次觀看)$/,
    /^(Follow|追蹤|Following|追蹤中)$/i,
  ];

  return uiPatterns.some((p) => p.test(text.trim()));
}

/**
 * 提取貼文圖片
 */
function extractIGImages(post) {
  const images = [];
  const seen = new Set();

  post.querySelectorAll("img").forEach((img) => {
    const src = img.src || img.getAttribute("srcset")?.split(",")[0]?.trim()?.split(" ")[0] || "";
    if (!src || src.startsWith("data:")) return;

    // 過濾頭像等小圖
    const width = img.naturalWidth || img.width || 0;
    const height = img.naturalHeight || img.height || 0;
    if (width > 0 && width < 150) return;
    if (height > 0 && height < 150) return;

    // 過濾 profile picture（通常在 header 且較小）
    const parent = img.closest("header");
    if (parent) return;

    if (seen.has(src)) return;
    seen.add(src);

    images.push(src);
  });

  // 也嘗試從 video poster 提取
  post.querySelectorAll("video").forEach((video) => {
    const poster = video.getAttribute("poster") || "";
    if (poster && !seen.has(poster)) {
      seen.add(poster);
      images.push(poster);
    }
  });

  return images;
}

/**
 * 提取貼文時間
 */
function extractIGTimestamp(post) {
  // <time> 標籤
  const timeEl = post.querySelector("time");
  if (timeEl) {
    return timeEl.getAttribute("datetime") || timeEl.textContent.trim();
  }

  return null;
}
