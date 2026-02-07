"""
URL 輸入元件
=============
URL 輸入框 + 平台自動識別徽章。
"""

import customtkinter as ctk

from gui.theme import FONT_NORMAL, FONT_SMALL, PLATFORM_COLORS, PAD_INNER

# 確保 scraper 可用
import sys, os
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
import scraper


class URLInput(ctk.CTkFrame):
    """URL 輸入框 + 平台識別徽章"""

    def __init__(self, parent, on_identify=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_identify = on_identify
        self._build_ui()

    def _build_ui(self):
        ctk.CTkLabel(self, text="網址：", font=FONT_NORMAL).pack(side="left")

        self._entry = ctk.CTkEntry(
            self, font=FONT_NORMAL, placeholder_text="輸入文章 URL...",
        )
        self._entry.pack(side="left", fill="x", expand=True, padx=(PAD_INNER, PAD_INNER))
        self._entry.bind("<KeyRelease>", self._on_key_release)

        self._badge = ctk.CTkLabel(
            self, text="", font=FONT_SMALL, width=80,
            corner_radius=6,
        )
        self._badge.pack(side="left", padx=(0, PAD_INNER))

    def _on_key_release(self, event=None):
        """URL 變更時自動識別平台"""
        url = self.get_url()
        if url:
            platform = scraper.identify_platform(url)
            color = PLATFORM_COLORS.get(platform, PLATFORM_COLORS["其他"])
            self._badge.configure(text=platform, text_color=color)
            if self._on_identify:
                self._on_identify(platform)
        else:
            self._badge.configure(text="")

    def get_url(self) -> str:
        """取得目前輸入的 URL"""
        return self._entry.get().strip()

    def set_url(self, url: str):
        """設定 URL"""
        self._entry.delete(0, "end")
        self._entry.insert(0, url)
        self._on_key_release()

    def clear(self):
        """清除輸入"""
        self._entry.delete(0, "end")
        self._badge.configure(text="")
