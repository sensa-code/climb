/**
 * CLIMB Extension — Content Script (content.js)
 * ==============================================
 * 注入到所有頁面，偵測平台並呼叫對應的提取器。
 * 提取器定義在 extractors/ 目錄下，在此之前載入。
 */

/**
 * 偵測目前頁面的平台
 */
function detectPlatform() {
  const hostname = window.location.hostname.toLowerCase();

  if (hostname.includes("facebook.com") || hostname.includes("fb.com")) {
    return "Facebook";
  }
  if (hostname.includes("instagram.com")) {
    return "Instagram";
  }
  if (hostname.includes("ptt.cc")) {
    return "PTT";
  }
  if (hostname.includes("medium.com")) {
    return "Medium";
  }
  if (hostname.includes("cliniciansbrief.com")) {
    return "Clinician's Brief";
  }

  return "其他";
}

/**
 * 根據平台呼叫對應的提取器
 */
function extractArticle() {
  const platform = detectPlatform();
  let result = null;

  switch (platform) {
    case "Facebook":
      if (typeof extractFacebook === "function") {
        result = extractFacebook();
      }
      break;
    case "Instagram":
      if (typeof extractInstagram === "function") {
        result = extractInstagram();
      }
      break;
    default:
      // 其他平台使用通用提取器
      break;
  }

  // 如果專用提取器失敗或不存在，使用通用提取器
  if (!result || !result.content) {
    if (typeof extractGeneric === "function") {
      result = extractGeneric();
    }
  }

  // 補充共通欄位
  if (result) {
    result.url = result.url || window.location.href;
    result.platform = result.platform || platform;
    result.source = "chrome-ext";
  }

  return result;
}

/**
 * 監聽來自 background.js 的提取請求
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "extract") {
    try {
      const data = extractArticle();
      sendResponse(data);
    } catch (e) {
      console.error("[CLIMB] Extraction error:", e);
      sendResponse(null);
    }
  }
});
