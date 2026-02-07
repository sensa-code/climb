"""
單篇擷取頁籤
=============
輸入 URL → 識別平台 → 背景擷取 → 顯示結果。
"""

import os
import queue
import threading
import time

import customtkinter as ctk

import scraper
from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_HEADING,
    STATUS_ICONS, PLATFORM_COLORS,
    PAD_X, PAD_Y, PAD_SECTION, PAD_INNER,
)
from gui.widgets.url_input import URLInput
from gui.widgets.progress_panel import ProgressPanel


class SingleFetchTab:
    """單篇擷取頁籤"""

    TASK_ID = "single_fetch"

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent
        self.task_id = self.TASK_ID
        self._platform = ""

        # 自己的 queue
        self._progress_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()

        self._build_ui()

    def _build_ui(self):
        # --- URL 輸入區 ---
        url_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        url_frame.pack(fill="x", padx=PAD_X, pady=(PAD_Y, PAD_INNER))

        self._url_input = URLInput(
            url_frame,
            on_identify=self._on_platform_identified,
        )
        self._url_input.pack(side="left", fill="x", expand=True)

        self._fetch_btn = ctk.CTkButton(
            url_frame, text="擷取", width=80, font=FONT_NORMAL,
            command=self._start_fetch,
        )
        self._fetch_btn.pack(side="right", padx=(PAD_INNER, 0))

        # --- 平台資訊 ---
        self._platform_label = ctk.CTkLabel(
            self.parent, text="", font=FONT_SMALL, anchor="w",
        )
        self._platform_label.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        # --- 選項區 ---
        options_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        options_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        ctk.CTkLabel(options_frame, text="輸出目錄：", font=FONT_SMALL).pack(side="left")

        self._output_entry = ctk.CTkEntry(
            options_frame, font=FONT_SMALL, width=300,
        )
        self._output_entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._output_entry.insert(0, self.app.get_output_dir())

        ctk.CTkButton(
            options_frame, text="瀏覽...", width=70, font=FONT_SMALL,
            command=self._browse_output,
        ).pack(side="left", padx=(0, PAD_SECTION))

        self._force_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            options_frame, text="忽略去重（強制重新擷取）",
            variable=self._force_var, font=FONT_SMALL,
            checkbox_width=18, checkbox_height=18,
        ).pack(side="left")

        # --- 進度面板 ---
        self._progress = ProgressPanel(
            self.parent,
            on_cancel=self._cancel_fetch,
        )

        # --- 結果區 ---
        self._result_frame = ctk.CTkFrame(self.parent)
        self._result_label = ctk.CTkLabel(
            self._result_frame, text="", font=FONT_NORMAL,
            anchor="w", justify="left",
        )
        self._result_label.pack(fill="x", padx=PAD_INNER, pady=PAD_INNER)

        # 結果按鈕列
        self._result_buttons = ctk.CTkFrame(self._result_frame, fg_color="transparent")
        self._result_buttons.pack(fill="x", padx=PAD_INNER, pady=(0, PAD_INNER))

        self._open_folder_btn = ctk.CTkButton(
            self._result_buttons, text="開啟資料夾", width=100, font=FONT_SMALL,
            command=self._open_result_folder,
        )
        self._open_folder_btn.pack(side="left", padx=(0, PAD_INNER))

        self._copy_path_btn = ctk.CTkButton(
            self._result_buttons, text="複製路徑", width=100, font=FONT_SMALL,
            command=self._copy_result_path,
        )
        self._copy_path_btn.pack(side="left")

        # 儲存結果路徑
        self._result_path = ""

    def poll_queues(self):
        """輪詢自己的 queue（由主視窗呼叫）"""
        # 進度
        try:
            while True:
                current, total, message = self._progress_queue.get_nowait()
                self._progress.update_progress(current, total, message)
        except queue.Empty:
            pass

        # 結果
        try:
            while True:
                url, status, data = self._result_queue.get_nowait()
                self._on_result(url, status, data)
        except queue.Empty:
            pass

    def _on_platform_identified(self, platform_name: str):
        """平台識別完成"""
        self._platform = platform_name
        strategies = {
            "PTT": "Jina → BS4 → Playwright",
            "Medium": "Jina → BS4 → Playwright",
            "Facebook": "不支援（需使用 Chrome Extension）",
            "Instagram": "不支援（需使用 Chrome Extension）",
            "獸醫學會": "BS4 → Jina → Playwright",
        }
        strategy = strategies.get(platform_name, "Jina → BS4 → Playwright")

        blocked = platform_name in ("Facebook", "Instagram")
        status_text = "[不支援]" if blocked else "[允許]"

        self._platform_label.configure(
            text=f"平台：{platform_name}（策略：{strategy}）  {status_text}"
        )
        self._fetch_btn.configure(state="disabled" if blocked else "normal")

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

    def _start_fetch(self):
        """開始擷取"""
        url = self._url_input.get_url()
        if not url:
            return

        output_dir = self._output_entry.get().strip()
        if not output_dir:
            output_dir = self.app.get_output_dir()

        force = self._force_var.get()

        # 檢查去重
        if not force and scraper.is_already_fetched(url, output_dir):
            self._show_result(
                "已跳過：此 URL 已擷取過",
                f"URL：{url}\n已存在於 {output_dir}\n勾選「忽略去重」可強制重新擷取",
                ""
            )
            return

        # 顯示進度
        self._progress.show()
        self._result_frame.pack_forget()
        self._fetch_btn.configure(state="disabled")

        # 提交背景任務
        self.app.task_runner.submit(
            self.TASK_ID,
            self._fetch_worker,
            url, output_dir,
            progress_queue=self._progress_queue,
            result_queue=self._result_queue,
        )

    @staticmethod
    def _fetch_worker(url, output_dir, cancel_event, progress_queue, result_queue):
        """背景執行緒中執行擷取"""
        try:
            progress_queue.put((1, 3, f"正在擷取：{url}"))

            article = scraper.fetch_article(url)

            if cancel_event.is_set():
                result_queue.put((url, "cancelled", {}))
                return

            if article:
                progress_queue.put((2, 3, "正在儲存..."))
                save_path = scraper.save_article(article, output_dir)
                scraper.mark_as_fetched(url, output_dir)
                progress_queue.put((3, 3, "完成"))

                result_queue.put((url, "success", {
                    "title": article.get("title", ""),
                    "strategy": article.get("fetched_by", ""),
                    "images": len(article.get("images", [])),
                    "path": save_path or "",
                }))
            else:
                progress_queue.put((3, 3, "擷取失敗"))
                result_queue.put((url, "failed", {}))

        except Exception as e:
            scraper.logger.error(f"擷取失敗：{e}")
            result_queue.put((url, "failed", {"error": str(e)}))

    def _on_result(self, url, status, data):
        """處理結果"""
        self._progress.set_complete()
        self._fetch_btn.configure(state="normal")

        if status == "success":
            title = data.get("title", "（無標題）")
            strategy = data.get("strategy", "未知")
            images = data.get("images", 0)
            path = data.get("path", "")
            self._show_result(
                "擷取成功",
                f"標題：{title}\n策略：{strategy}\n圖片：{images} 張\n路徑：{path}",
                path,
            )
        elif status == "cancelled":
            self._show_result("已取消", f"URL：{url}", "")
        else:
            error = data.get("error", "所有策略都失敗")
            self._show_result("擷取失敗", f"URL：{url}\n錯誤：{error}", "")

    def _show_result(self, title: str, detail: str, path: str):
        """顯示結果"""
        self._result_path = path
        self._result_label.configure(text=f"{title}\n{detail}")
        self._result_frame.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, PAD_Y))

        has_path = bool(path)
        self._open_folder_btn.configure(state="normal" if has_path else "disabled")
        self._copy_path_btn.configure(state="normal" if has_path else "disabled")

    def _cancel_fetch(self):
        """取消擷取"""
        self.app.task_runner.cancel(self.TASK_ID)

    def _open_result_folder(self):
        """開啟結果資料夾"""
        if self._result_path:
            import platform as plat
            import subprocess
            path = os.path.expanduser(self._result_path)
            if os.path.exists(path):
                if plat.system() == "Windows":
                    os.startfile(path)
                elif plat.system() == "Darwin":
                    subprocess.run(["open", path])
                else:
                    subprocess.run(["xdg-open", path])

    def _copy_result_path(self):
        """複製結果路徑到剪貼簿"""
        if self._result_path:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(self._result_path)
