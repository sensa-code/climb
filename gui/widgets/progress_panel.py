"""
進度面板元件
=============
進度條 + 狀態文字 + 取消按鈕。
"""

import customtkinter as ctk

from gui.theme import FONT_NORMAL, FONT_SMALL, PAD_INNER, PAD_X, PAD_Y


class ProgressPanel(ctk.CTkFrame):
    """進度顯示面板"""

    def __init__(self, parent, on_cancel=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._on_cancel = on_cancel
        self._build_ui()
        # 初始隱藏
        self.pack_forget()

    def _build_ui(self):
        # 標題行
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=PAD_INNER, pady=(PAD_INNER, 0))

        ctk.CTkLabel(header, text="進度", font=FONT_NORMAL).pack(side="left")

        self._cancel_btn = ctk.CTkButton(
            header, text="取消", width=60, font=FONT_SMALL,
            fg_color="#CC4444", hover_color="#AA3333",
            command=self._handle_cancel,
        )
        self._cancel_btn.pack(side="right")

        # 進度條
        self._progress_bar = ctk.CTkProgressBar(self)
        self._progress_bar.pack(fill="x", padx=PAD_INNER, pady=(PAD_INNER, 0))
        self._progress_bar.set(0)

        # 狀態文字
        self._status_label = ctk.CTkLabel(
            self, text="準備中...", font=FONT_SMALL, anchor="w",
        )
        self._status_label.pack(fill="x", padx=PAD_INNER, pady=(0, PAD_INNER))

    def show(self):
        """顯示進度面板"""
        self.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, 0))
        self._progress_bar.set(0)
        self._status_label.configure(text="準備中...")
        self._cancel_btn.configure(state="normal")

    def hide(self):
        """隱藏進度面板"""
        self.pack_forget()

    def update_progress(self, current: int, total: int, message: str = ""):
        """更新進度

        Args:
            current: 目前完成數
            total: 總數
            message: 狀態訊息
        """
        if total > 0:
            self._progress_bar.set(current / total)
        pct = int(current / total * 100) if total > 0 else 0
        status = f"{current}/{total} ({pct}%)"
        if message:
            status += f"  {message}"
        self._status_label.configure(text=status)

    def set_status(self, text: str):
        """設定狀態文字"""
        self._status_label.configure(text=text)

    def set_complete(self):
        """標記完成"""
        self._progress_bar.set(1)
        self._cancel_btn.configure(state="disabled")

    def _handle_cancel(self):
        """處理取消按鈕"""
        self._cancel_btn.configure(state="disabled")
        self._status_label.configure(text="正在取消...")
        if self._on_cancel:
            self._on_cancel()
