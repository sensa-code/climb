"""
即時日誌頁籤
=============
顯示 scraper 即時日誌，支援等級篩選、自動捲動、清除、匯出。
"""

import queue
import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from gui.theme import (
    FONT_MONO_SMALL, FONT_SMALL, LOG_COLORS,
    PAD_X, PAD_Y, PAD_INNER,
)


class LogViewerTab:
    """日誌檢視器頁籤"""

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent
        self._auto_scroll = True
        self._filter_level = "全部"
        self._all_logs: list[tuple[str, str]] = []  # (level, message)
        self._build_ui()

    def _build_ui(self):
        # --- 工具列 ---
        toolbar = ctk.CTkFrame(self.parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=PAD_X, pady=(PAD_Y, PAD_INNER))

        ctk.CTkLabel(toolbar, text="等級：", font=FONT_SMALL).pack(side="left")

        self._level_var = ctk.StringVar(value="全部")
        self._level_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["全部", "DEBUG", "INFO", "WARNING", "ERROR"],
            variable=self._level_var,
            command=self._on_filter_change,
            width=100,
            font=FONT_SMALL,
        )
        self._level_menu.pack(side="left", padx=(PAD_INNER, PAD_X))

        self._auto_scroll_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            toolbar,
            text="自動捲動",
            variable=self._auto_scroll_var,
            font=FONT_SMALL,
            checkbox_width=18,
            checkbox_height=18,
        ).pack(side="left", padx=(0, PAD_X))

        ctk.CTkButton(
            toolbar, text="清除", width=60, font=FONT_SMALL,
            command=self._clear_logs,
        ).pack(side="left", padx=(0, PAD_INNER))

        ctk.CTkButton(
            toolbar, text="匯出", width=60, font=FONT_SMALL,
            command=self._export_logs,
        ).pack(side="left")

        # --- 日誌文字框 ---
        self._textbox = ctk.CTkTextbox(
            self.parent,
            font=FONT_MONO_SMALL,
            wrap="word",
            state="disabled",
            activate_scrollbars=True,
        )
        self._textbox.pack(fill="both", expand=True, padx=PAD_X, pady=(0, PAD_Y))

        # 設定日誌等級顏色 tag
        for level, color in LOG_COLORS.items():
            self._textbox.tag_config(level, foreground=color)

    def append_log(self, level: str, message: str):
        """新增一筆日誌（由主視窗的輪詢迴圈呼叫）"""
        self._all_logs.append((level, message))

        # 檢查是否通過篩選
        if self._filter_level != "全部" and level != self._filter_level:
            return

        self._insert_line(level, message)

    def _insert_line(self, level: str, message: str):
        """插入一行日誌到文字框"""
        self._textbox.configure(state="normal")
        self._textbox.insert("end", message + "\n", level)
        self._textbox.configure(state="disabled")

        if self._auto_scroll_var.get():
            self._textbox.see("end")

    def _on_filter_change(self, choice: str):
        """篩選等級變更時重新渲染"""
        self._filter_level = choice
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")

        for level, msg in self._all_logs:
            if choice == "全部" or level == choice:
                self._insert_line(level, msg)

    def _clear_logs(self):
        """清除所有日誌"""
        self._all_logs.clear()
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")

    def _export_logs(self):
        """匯出日誌到檔案"""
        from tkinter import filedialog
        filepath = filedialog.asksaveasfilename(
            defaultextension=".log",
            filetypes=[("日誌檔", "*.log"), ("文字檔", "*.txt"), ("所有檔案", "*.*")],
            initialfile=f"climb_log_{datetime.now():%Y%m%d_%H%M%S}.log",
        )
        if filepath:
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    for _level, msg in self._all_logs:
                        f.write(msg + "\n")
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("匯出失敗", str(e))
