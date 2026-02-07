"""
批次擷取頁籤
=============
從檔案或手動輸入多個 URL，背景逐一擷取，顯示進度和結果列表。
"""

import os
import queue
import time
import uuid

import customtkinter as ctk

import scraper
from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_HEADING,
    PAD_X, PAD_Y, PAD_SECTION, PAD_INNER,
)
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.result_table import ResultTable


class BatchFetchTab:
    """批次擷取頁籤"""

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent
        self.task_id = None  # 動態產生

        # 自己的 queue
        self._progress_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()

        self._build_ui()

    def _build_ui(self):
        # --- URL 來源選擇 ---
        source_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        source_frame.pack(fill="x", padx=PAD_X, pady=(PAD_Y, PAD_INNER))

        ctk.CTkLabel(source_frame, text="URL 來源：", font=FONT_NORMAL).pack(side="left")

        self._source_var = ctk.StringVar(value="file")
        ctk.CTkRadioButton(
            source_frame, text="從檔案載入", variable=self._source_var,
            value="file", font=FONT_SMALL, command=self._toggle_source,
        ).pack(side="left", padx=(PAD_INNER, PAD_SECTION))

        ctk.CTkRadioButton(
            source_frame, text="手動輸入", variable=self._source_var,
            value="manual", font=FONT_SMALL, command=self._toggle_source,
        ).pack(side="left")

        # --- 檔案模式 ---
        self._file_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        self._file_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        ctk.CTkLabel(self._file_frame, text="檔案：", font=FONT_SMALL).pack(side="left")

        self._file_entry = ctk.CTkEntry(
            self._file_frame, font=FONT_SMALL, width=400,
            placeholder_text="選擇包含 URL 列表的檔案...",
        )
        self._file_entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))

        ctk.CTkButton(
            self._file_frame, text="瀏覽...", width=70, font=FONT_SMALL,
            command=self._browse_file,
        ).pack(side="left")

        # --- 手動模式 ---
        self._manual_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        # 初始隱藏

        ctk.CTkLabel(
            self._manual_frame, text="每行一個 URL：",
            font=FONT_SMALL, anchor="w",
        ).pack(fill="x")

        self._url_textbox = ctk.CTkTextbox(
            self._manual_frame, font=FONT_SMALL, height=120,
        )
        self._url_textbox.pack(fill="x", pady=(PAD_INNER, 0))

        paste_frame = ctk.CTkFrame(self._manual_frame, fg_color="transparent")
        paste_frame.pack(fill="x", pady=(PAD_INNER, 0))

        ctk.CTkButton(
            paste_frame, text="從剪貼簿貼上", width=110, font=FONT_SMALL,
            command=self._paste_from_clipboard,
        ).pack(side="left", padx=(0, PAD_INNER))

        ctk.CTkButton(
            paste_frame, text="清除", width=60, font=FONT_SMALL,
            command=lambda: self._url_textbox.delete("1.0", "end"),
        ).pack(side="left")

        self._url_count_label = ctk.CTkLabel(
            paste_frame, text="URL 數量：0", font=FONT_SMALL,
        )
        self._url_count_label.pack(side="right")

        self._url_textbox.bind("<KeyRelease>", self._update_url_count)

        # --- 輸出目錄 + 開始按鈕 ---
        action_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        action_frame.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, PAD_INNER))

        ctk.CTkLabel(action_frame, text="輸出目錄：", font=FONT_SMALL).pack(side="left")

        self._output_entry = ctk.CTkEntry(
            action_frame, font=FONT_SMALL, width=300,
        )
        self._output_entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._output_entry.insert(0, self.app.get_output_dir())

        ctk.CTkButton(
            action_frame, text="瀏覽...", width=70, font=FONT_SMALL,
            command=self._browse_output,
        ).pack(side="left", padx=(0, PAD_SECTION))

        self._start_btn = ctk.CTkButton(
            action_frame, text="開始批次擷取", width=120, font=FONT_NORMAL,
            command=self._start_batch,
        )
        self._start_btn.pack(side="right")

        # --- 進度面板 ---
        self._progress = ProgressPanel(
            self.parent,
            on_cancel=self._cancel_batch,
        )

        # --- 結果表格 ---
        self._result_table = ResultTable(self.parent, height=200)

        # --- 統計列 ---
        self._stats_label = ctk.CTkLabel(
            self.parent, text="", font=FONT_SMALL, anchor="w",
        )

    def poll_queues(self):
        """輪詢自己的 queue（由主視窗呼叫）"""
        # 進度
        for _ in range(50):
            try:
                current, total, message = self._progress_queue.get_nowait()
                self._progress.update_progress(current, total, message)
            except queue.Empty:
                break
            except Exception:
                break

        # 結果
        for _ in range(50):
            try:
                url, status, data = self._result_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._on_result(url, status, data)
            except Exception as e:
                scraper.logger.error(f"處理結果時發生錯誤：{e}")

    def _toggle_source(self):
        """切換檔案/手動模式"""
        if self._source_var.get() == "file":
            self._manual_frame.pack_forget()
            self._file_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER),
                                  after=self.parent.winfo_children()[0])
        else:
            self._file_frame.pack_forget()
            self._manual_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER),
                                    after=self.parent.winfo_children()[0])

    def _browse_file(self):
        """瀏覽 URL 列表檔案"""
        from tkinter import filedialog
        filepath = filedialog.askopenfilename(
            filetypes=[("文字檔", "*.txt"), ("所有檔案", "*.*")],
            title="選擇 URL 列表檔案",
        )
        if filepath:
            self._file_entry.delete(0, "end")
            self._file_entry.insert(0, filepath)

    def _browse_output(self):
        """瀏覽輸出目錄"""
        from tkinter import filedialog
        path = filedialog.askdirectory(
            initialdir=self._output_entry.get(),
            title="選擇輸出目錄",
        )
        if path:
            self._output_entry.delete(0, "end")
            self._output_entry.insert(0, path)

    def _paste_from_clipboard(self):
        """從剪貼簿貼上 URL"""
        try:
            text = self.parent.clipboard_get()
            self._url_textbox.insert("end", text)
            self._update_url_count()
        except Exception:
            pass

    def _update_url_count(self, event=None):
        """更新 URL 數量顯示"""
        urls = self._get_manual_urls()
        self._url_count_label.configure(text=f"URL 數量：{len(urls)}")

    def _get_manual_urls(self) -> list[str]:
        """從手動輸入取得 URL 列表"""
        text = self._url_textbox.get("1.0", "end").strip()
        if not text:
            return []
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
        return urls

    def _get_file_urls(self) -> list[str]:
        """從檔案取得 URL 列表"""
        filepath = self._file_entry.get().strip()
        if not filepath or not os.path.isfile(filepath):
            return []
        urls = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
        return urls

    def _start_batch(self):
        """開始批次擷取"""
        # 取得 URL 列表
        if self._source_var.get() == "file":
            urls = self._get_file_urls()
        else:
            urls = self._get_manual_urls()

        if not urls:
            from tkinter import messagebox
            messagebox.showwarning("無 URL", "請提供至少一個 URL")
            return

        output_dir = self._output_entry.get().strip()
        if not output_dir:
            output_dir = self.app.get_output_dir()

        # 準備 UI
        self.task_id = f"batch_{uuid.uuid4().hex[:8]}"
        self._progress.show()
        self._result_table.clear()
        self._result_table.pack(fill="both", expand=True, padx=PAD_X, pady=(PAD_INNER, 0))
        self._stats_label.configure(text="")
        self._stats_label.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, PAD_Y))
        self._start_btn.configure(state="disabled")

        # 提交背景任務
        self.app.task_runner.submit(
            self.task_id,
            self._batch_worker,
            urls, output_dir,
            progress_queue=self._progress_queue,
            result_queue=self._result_queue,
        )

    @staticmethod
    def _batch_worker(urls, output_dir, cancel_event, progress_queue, result_queue):
        """背景執行緒中逐一擷取 URL"""
        total = len(urls)
        for i, url in enumerate(urls, 1):
            if cancel_event.is_set():
                break

            platform_name = scraper.identify_platform(url)

            # 檢查是否為不支援的平台
            if platform_name in ("Facebook", "Instagram"):
                result_queue.put((url, "skipped", {
                    "platform": platform_name,
                    "reason": "需要 Chrome Extension",
                }))
                progress_queue.put((i, total, f"跳過：{url}"))
                continue

            progress_queue.put((i, total, f"擷取中：{url}"))

            # 檢查去重
            if scraper.is_already_fetched(url, output_dir):
                result_queue.put((url, "skipped", {
                    "platform": platform_name,
                    "reason": "已擷取過",
                }))
                continue

            try:
                article = scraper.fetch_article(url)
                if article:
                    save_path = scraper.save_article(article, output_dir)
                    scraper.mark_as_fetched(url, output_dir)
                    result_queue.put((url, "success", {
                        "platform": platform_name,
                        "path": save_path or "",
                    }))
                else:
                    result_queue.put((url, "failed", {
                        "platform": platform_name,
                    }))
            except Exception as e:
                scraper.logger.error(f"擷取失敗 {url}: {e}")
                result_queue.put((url, "failed", {
                    "platform": platform_name,
                    "error": str(e),
                }))

            # 禮貌延遲
            if i < total and not cancel_event.is_set():
                time.sleep(scraper.POLITENESS_DELAY)

        # 完成通知
        progress_queue.put((total, total, "批次擷取完成"))
        result_queue.put(("__BATCH_DONE__", "done", {}))

    def _on_result(self, url, status, data):
        """處理結果"""
        if url == "__BATCH_DONE__":
            self._progress.set_complete()
            self._start_btn.configure(state="normal")
            self._stats_label.configure(text=self._result_table.get_stats_text())
            return

        platform_name = data.get("platform", scraper.identify_platform(url))
        path = data.get("path", "")

        self._result_table.add_result(url, platform_name, status, path)
        self._stats_label.configure(text=self._result_table.get_stats_text())

    def _cancel_batch(self):
        """取消批次擷取"""
        if self.task_id:
            self.app.task_runner.cancel(self.task_id)
