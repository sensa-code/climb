"""
CLIMB GUI 主視窗
=================
頁籤系統、日誌橋接、共享狀態管理。
所有頁籤在此註冊，背景執行緒透過 queue 與 GUI 通訊。
"""

import os
import sys
import queue
import logging

import customtkinter as ctk

# 確保 scraper.py 所在目錄在 sys.path 中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import scraper

from gui.theme import (
    FONT_NORMAL, FONT_HEADING, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT,
    WINDOW_DEFAULT_SIZE, PAD_X, PAD_Y,
)
from gui.workers.log_handler import GUILogHandler
from gui.workers.task_runner import TaskRunner


class ClimbApp(ctk.CTk):
    """CLIMB 主應用程式視窗"""

    def __init__(self):
        super().__init__()

        self.title("CLIMB — 獸醫文章擷取工具")
        self.geometry(WINDOW_DEFAULT_SIZE)
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # 共享狀態
        self.log_queue: queue.Queue = queue.Queue()
        self.task_runner = TaskRunner(max_workers=2)
        self.config = dict(scraper._CONFIG)

        # 日誌橋接：在 scraper.logger 安裝 GUI handler
        self._gui_log_handler = GUILogHandler(self.log_queue)
        scraper.logger.addHandler(self._gui_log_handler)
        # 確保 logger 不會被 level 過濾掉低等級訊息
        if scraper.logger.level > logging.DEBUG:
            scraper.logger.setLevel(logging.DEBUG)

        # 頁籤實例容器
        self._tabs: dict[str, object] = {}

        # 需要輪詢的頁籤（有自己的 queue 的頁籤）
        self._pollable_tabs: list = []

        # 建立 UI
        self._build_ui()

        # 啟動輪詢迴圈
        self._poll_queues()

        # 視窗關閉事件
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 鍵盤快捷鍵
        self.bind("<Escape>", self._on_escape)

    def _build_ui(self):
        """建立頁籤系統"""
        self._tabview = ctk.CTkTabview(self, anchor="nw")
        self._tabview.pack(fill="both", expand=True, padx=PAD_X, pady=PAD_Y)

        # 匯入並註冊所有頁籤（延遲匯入避免循環依賴）
        from gui.tabs.single_fetch import SingleFetchTab
        from gui.tabs.batch_fetch import BatchFetchTab
        from gui.tabs.ptt_board import PttBoardTab
        from gui.tabs.settings import SettingsTab
        from gui.tabs.article_browser import ArticleBrowserTab
        from gui.tabs.log_viewer import LogViewerTab

        tab_defs = [
            ("單篇擷取", SingleFetchTab),
            ("批次擷取", BatchFetchTab),
            ("PTT 看板", PttBoardTab),
            ("設定", SettingsTab),
            ("文章瀏覽", ArticleBrowserTab),
            ("日誌", LogViewerTab),
        ]

        for name, tab_class in tab_defs:
            frame = self._tabview.add(name)
            tab_instance = tab_class(frame, self)
            self._tabs[name] = tab_instance

            # 收集需要輪詢的頁籤
            if hasattr(tab_instance, "poll_queues"):
                self._pollable_tabs.append(tab_instance)

        # 預設顯示第一個頁籤
        self._tabview.set("單篇擷取")

    def get_tab(self, name: str):
        """取得頁籤實例"""
        return self._tabs.get(name)

    def get_output_dir(self) -> str:
        """取得目前輸出目錄"""
        return self.config.get("output_dir", scraper.DEFAULT_OUTPUT_DIR)

    def _poll_queues(self):
        """輪詢所有 queue，將資料分派到對應的 GUI 元件"""
        # 處理日誌 queue
        for _ in range(50):  # 每次最多處理 50 條，避免卡住 UI
            try:
                level, msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            try:
                log_tab = self._tabs.get("日誌")
                if log_tab:
                    log_tab.append_log(level, msg)
            except Exception:
                pass

        # 讓各頁籤輪詢自己的 queue
        for tab in self._pollable_tabs:
            try:
                tab.poll_queues()
            except Exception:
                pass

        # 每 100ms 輪詢一次
        self.after(100, self._poll_queues)

    def _on_escape(self, event=None):
        """Escape 鍵：取消目前正在執行的任務"""
        for tab in self._pollable_tabs:
            if hasattr(tab, "task_id") and tab.task_id:
                if self.task_runner.is_running(tab.task_id):
                    self.task_runner.cancel(tab.task_id)
                    scraper.logger.info("使用者按下 Escape 取消任務")
                    break

    def _on_close(self):
        """視窗關閉事件"""
        self.task_runner.shutdown()
        scraper.logger.removeHandler(self._gui_log_handler)
        self.destroy()


def run():
    """啟動 CLIMB GUI 應用程式"""
    app = ClimbApp()
    app.mainloop()
