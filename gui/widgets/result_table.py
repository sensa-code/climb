"""
結果表格元件
=============
可捲動的結果表格，顯示 URL、平台、狀態、路徑。
"""

import os
import subprocess
import platform

import customtkinter as ctk

from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_MONO_SMALL,
    STATUS_ICONS, PAD_INNER, PAD_X, PAD_Y,
)


class ResultTable(ctk.CTkScrollableFrame):
    """結果列表（可捲動）"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._rows: list[ctk.CTkFrame] = []
        self._stats = {"success": 0, "failed": 0, "skipped": 0}

        # 表頭
        self._header = ctk.CTkFrame(self, fg_color="transparent")
        self._header.pack(fill="x", pady=(0, PAD_INNER))

        for text, width in [("URL", 300), ("平台", 70), ("狀態", 50), ("路徑", 250)]:
            ctk.CTkLabel(
                self._header, text=text, font=FONT_SMALL,
                width=width, anchor="w",
            ).pack(side="left", padx=(0, PAD_INNER))

    def add_result(self, url: str, platform_name: str, status: str, path: str = ""):
        """新增一筆結果

        Args:
            url: 文章 URL
            platform_name: 平台名稱
            status: 狀態 (success/failed/skipped)
            path: 儲存路徑
        """
        icon = STATUS_ICONS.get(status, "❓")
        self._stats[status] = self._stats.get(status, 0) + 1

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=1)

        # URL（截短顯示）
        display_url = url if len(url) <= 45 else url[:42] + "..."
        url_label = ctk.CTkLabel(
            row, text=display_url, font=FONT_MONO_SMALL,
            width=300, anchor="w",
        )
        url_label.pack(side="left", padx=(0, PAD_INNER))

        # 平台
        ctk.CTkLabel(
            row, text=platform_name, font=FONT_SMALL,
            width=70, anchor="w",
        ).pack(side="left", padx=(0, PAD_INNER))

        # 狀態
        ctk.CTkLabel(
            row, text=icon, font=FONT_SMALL,
            width=50, anchor="center",
        ).pack(side="left", padx=(0, PAD_INNER))

        # 路徑（可點擊開啟）
        if path:
            display_path = os.path.basename(path.rstrip("/\\"))
            path_btn = ctk.CTkButton(
                row, text=display_path, font=FONT_SMALL,
                width=250, anchor="w", fg_color="transparent",
                text_color=("#1a73e8", "#8ab4f8"),
                hover_color=("gray85", "gray25"),
                command=lambda p=path: self._open_folder(p),
            )
            path_btn.pack(side="left")
        else:
            ctk.CTkLabel(
                row, text="-", font=FONT_SMALL,
                width=250, anchor="w",
            ).pack(side="left")

        self._rows.append(row)

    def get_stats(self) -> dict:
        """取得統計資料"""
        return dict(self._stats)

    def get_stats_text(self) -> str:
        """取得統計文字"""
        s = self._stats
        return f"成功 {s.get('success', 0)} / 失敗 {s.get('failed', 0)} / 跳過 {s.get('skipped', 0)}"

    def clear(self):
        """清除所有結果"""
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._stats = {"success": 0, "failed": 0, "skipped": 0}

    @staticmethod
    def _open_folder(path: str):
        """用系統檔案管理員開啟資料夾"""
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            # 嘗試開啟父目錄
            path = os.path.dirname(path)
        if os.path.exists(path):
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
