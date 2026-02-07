/**
 * CLIMB Extension — Facebook Extractor (facebook.js)
 * ===================================================
 * Facebook 專用的貼文內容提取器。
 * Facebook 的 DOM 結構經常變動，因此使用多組備選選擇器。
 */

/**
 * 提取 Facebook 貼文內容
 */
function extractFacebook() {
  // 嘗試展開「查看更多」按鈕
  expandSeeMore();

  // 找到貼文容器
  const post = findPostContainer();
  if (!post) {
    return null; // 回傳 null 讓 content.js 改用通用提取器
  }

  // 提取各部分
  const title = extractPostAuthor(post) || document.title;
  const content = extractPostText(post);
  const images = extractPostImages(post);
  const timestamp = extractPostTimestamp(post);

  if (!content || content.length < 10) {
    return null;
  }

  // 組裝 Markdown 內容
  let markdown = "";
  if (timestamp) {
    markdown += `> ${timestamp}\n\n`;
  }
  markdown += content;

  return {
    title: title,
    content: markdown,
    url: window.location.href,
    platform: "Facebook",
    source: "chrome-ext",
    images: images,
  };
}

/**
 * 展開所有「查看更多」按鈕
 */
function expandSeeMore() {
  // Facebook 的「查看更多」按鈕文字可能是中文或英文
  const expandTexts = [
    "查看更多", "See more", "...more", "...更多",
    "顯示更多", "See More", "続きを読む",
  ];

  // 方法 1：找 role="button" 且包含展開文字的元素
  document.querySelectorAll('[role="button"]').forEach((btn) => {
    const text = btn.textContent.trim();
    if (expandTexts.some((t) => text.includes(t))) {
      try { btn.click(); } catch (e) { /* ignore */ }
    }
  });

  // 方法 2：找 <span> 或 <div> 包含展開文字的可點擊元素
  document.querySelectorAll("span, div").forEach((el) => {
    const text = el.textContent.trim();
    if (text.length < 20 && expandTexts.some((t) => text === t)) {
      const style = window.getComputedStyle(el);
      if (style.cursor === "pointer") {
        try { el.click(); } catch (e) { /* ignore */ }
      }
    }
  });
}

/**
 * 找到貼文容器
 */
function findPostContainer() {
  const selectors = [
    '[role="article"]',
    '[data-ad-preview]',
    ".userContentWrapper",
    "._5pcr",
  ];

  for (const sel of selectors) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim().length > 20) {
      return el;
    }
  }

  return null;
}

/**
 * 提取貼文作者
 */
function extractPostAuthor(post) {
  // Facebook 貼文頂部通常有一個連結指向作者頁面
  const authorSelectors = [
    "h2 a",
    'a[role="link"] strong',
    "strong a",
    ".actor strong",
  ];

  for (const sel of authorSelectors) {
    const el = post.querySelector(sel);
    if (el) {
      const name = el.textContent.trim();
      if (name.length > 0 && name.length < 100) {
        return name;
      }
    }
  }

  return null;
}

/**
 * 提取貼文文字內容
 */
function extractPostText(post) {
  // 嘗試找到貼文文字區塊
  const textSelectors = [
    '[data-ad-comet-above-more-info]',
    '[data-ad-preview="message"]',
    ".userContent",
    '._5pbx',
  ];

  for (const sel of textSelectors) {
    const el = post.querySelector(sel);
    if (el && el.innerText.trim().length > 10) {
      return el.innerText.trim();
    }
  }

  // 備選：取整個貼文的文字，但排除導覽元素
  const clone = post.cloneNode(true);

  // 移除非內容元素
  clone.querySelectorAll(
    'nav, [role="navigation"], [role="toolbar"], ' +
    '[role="button"], .comment, .replies, ' +
    'form, input, textarea'
  ).forEach((el) => el.remove());

  const text = clone.innerText.trim();
  return text.length > 10 ? text : "";
}

/**
 * 提取貼文圖片
 * 過濾掉頭像、表情符號等小圖
 */
function extractPostImages(post) {
  const images = [];
  const seen = new Set();

  post.querySelectorAll("img").forEach((img) => {
    const src = img.src || "";
    if (!src || src.startsWith("data:")) return;

    // 過濾小圖：頭像、表情、UI 圖示
    const width = img.naturalWidth || img.width || parseInt(img.getAttribute("width")) || 0;
    const height = img.naturalHeight || img.height || parseInt(img.getAttribute("height")) || 0;

    if (width > 0 && width < 100) return;
    if (height > 0 && height < 100) return;

    // 過濾 emoji 圖片
    if (src.includes("/emoji/") || src.includes("emoji.php")) return;
    // 過濾 profile 小圖
    if (src.includes("/profilepic/") && width < 200) return;

    if (seen.has(src)) return;
    seen.add(src);

    images.push(src);
  });

  return images;
}

/**
 * 提取貼文時間
 */
function extractPostTimestamp(post) {
  // 方法 1：<abbr> 標籤（舊版 Facebook）
  const abbr = post.querySelector("abbr");
  if (abbr) {
    return abbr.getAttribute("title") || abbr.textContent.trim();
  }

  // 方法 2：aria-label 中包含時間的元素
  const timeLabels = post.querySelectorAll("[aria-label]");
  for (const el of timeLabels) {
    const label = el.getAttribute("aria-label");
    // 匹配常見的時間格式
    if (label && /\d{1,2}[\/\-:]\d{1,2}/.test(label)) {
      return label;
    }
  }

  // 方法 3：<time> 標籤或包含時間的 <span>
  const timeEl = post.querySelector("time");
  if (timeEl) {
    return timeEl.getAttribute("datetime") || timeEl.textContent.trim();
  }

  return null;
}
