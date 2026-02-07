/**
 * CLIMB Extension — Popup Logic (popup.js)
 * =========================================
 * 控制彈出視窗的互動邏輯：
 * - 檢查 API Server 連線狀態
 * - 顯示目前頁面資訊
 * - 觸發提取 + 儲存流程
 */

const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const saveBtn = document.getElementById("saveBtn");
const resultArea = document.getElementById("resultArea");
const resultIcon = document.getElementById("resultIcon");
const resultText = document.getElementById("resultText");
const platformName = document.getElementById("platformName");
const pageTitle = document.getElementById("pageTitle");
const hintText = document.getElementById("hintText");

let isConnected = false;

/**
 * 初始化：檢查伺服器狀態 + 取得頁面資訊
 */
async function init() {
  // 檢查伺服器狀態
  chrome.runtime.sendMessage({ action: "checkStatus" }, (response) => {
    if (response && response.status === "running") {
      setConnected(true, response.port);
    } else {
      setConnected(false);
    }
  });

  // 取得目前頁籤資訊
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs && tabs.length > 0) {
      const tab = tabs[0];
      pageTitle.textContent = truncate(tab.title || "—", 50);

      // 偵測平台
      const platform = detectPlatformFromUrl(tab.url || "");
      platformName.textContent = platform;
    }
  });
}

/**
 * 從 URL 偵測平台名稱
 */
function detectPlatformFromUrl(url) {
  const hostname = new URL(url).hostname.toLowerCase();

  if (hostname.includes("facebook.com") || hostname.includes("fb.com")) return "Facebook";
  if (hostname.includes("instagram.com")) return "Instagram";
  if (hostname.includes("ptt.cc")) return "PTT";
  if (hostname.includes("medium.com")) return "Medium";
  if (hostname.includes("cliniciansbrief.com")) return "Clinician's Brief";

  return "其他";
}

/**
 * 設定連線狀態 UI
 */
function setConnected(connected, port) {
  isConnected = connected;

  if (connected) {
    statusDot.classList.add("connected");
    statusText.textContent = `已連線 (port ${port || 3456})`;
    saveBtn.disabled = false;
    hintText.textContent = "點擊按鈕儲存目前頁面的文章內容";
  } else {
    statusDot.classList.remove("connected");
    statusText.textContent = "未連線";
    saveBtn.disabled = true;
    hintText.textContent = "請先在 CLIMB GUI 啟動 Extension Server";
  }
}

/**
 * 儲存按鈕點擊事件
 */
saveBtn.addEventListener("click", async () => {
  if (!isConnected) return;

  // 更新 UI 為儲存中狀態
  saveBtn.disabled = true;
  saveBtn.textContent = "儲存中...";
  saveBtn.classList.add("saving");
  resultArea.style.display = "none";

  // 發送提取 + 儲存請求到 background
  chrome.runtime.sendMessage({ action: "extractAndSave" }, (response) => {
    saveBtn.disabled = false;
    saveBtn.textContent = "儲存此頁面";
    saveBtn.classList.remove("saving");

    if (chrome.runtime.lastError) {
      showResult("error", `錯誤：${chrome.runtime.lastError.message}`);
      return;
    }

    if (response && response.status === "ok") {
      showResult("success", `已儲存：${response.title || "文章"}`);
    } else if (response && response.status === "error") {
      showResult("error", response.message || "儲存失敗");
    } else {
      showResult("error", "未知錯誤，請檢查 CLIMB Server 是否正常運行");
    }
  });
});

/**
 * 顯示結果
 */
function showResult(type, message) {
  resultArea.style.display = "flex";
  resultArea.className = `result ${type}`;
  resultIcon.textContent = type === "success" ? "\u2705" : "\u274c";
  resultText.textContent = message;
}

/**
 * 截斷文字
 */
function truncate(str, maxLen) {
  if (str.length <= maxLen) return str;
  return str.substring(0, maxLen) + "...";
}

// 初始化
init();
