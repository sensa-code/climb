/**
 * CLIMB Extension — Service Worker (background.js)
 * =================================================
 * 負責 popup ↔ content script 之間的訊息路由，
 * 以及與本地 API Server 的通訊。
 */

const API_BASE = "http://localhost:3456";

/**
 * 檢查 API Server 是否運行中
 */
async function checkServerStatus() {
  try {
    const resp = await fetch(`${API_BASE}/status`, { method: "GET" });
    if (resp.ok) {
      return await resp.json();
    }
    return null;
  } catch (e) {
    return null;
  }
}

/**
 * 將文章資料傳送到 API Server 儲存
 */
async function saveArticle(articleData) {
  const resp = await fetch(`${API_BASE}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(articleData),
  });
  return await resp.json();
}

/**
 * 監聽來自 popup 的訊息
 */
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "checkStatus") {
    checkServerStatus().then(sendResponse);
    return true; // 非同步回應
  }

  if (message.action === "extractAndSave") {
    // 取得目前活動頁籤
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || tabs.length === 0) {
        sendResponse({ status: "error", message: "No active tab" });
        return;
      }

      const tab = tabs[0];

      // 向 content script 發送提取請求
      chrome.tabs.sendMessage(
        tab.id,
        { action: "extract" },
        async (extractedData) => {
          if (chrome.runtime.lastError) {
            sendResponse({
              status: "error",
              message: `Content script error: ${chrome.runtime.lastError.message}`,
            });
            return;
          }

          if (!extractedData || !extractedData.content) {
            sendResponse({
              status: "error",
              message: "Failed to extract article content",
            });
            return;
          }

          // 傳送到 API Server
          try {
            const result = await saveArticle(extractedData);
            sendResponse(result);
          } catch (e) {
            sendResponse({
              status: "error",
              message: `Server error: ${e.message}`,
            });
          }
        }
      );
    });

    return true; // 非同步回應
  }
});
