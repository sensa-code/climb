#!/usr/bin/env python3
"""
CLIMB GUI 啟動入口
===================
用法：
  python app.py          # 直接執行
  climb                  # pip install 後的指令
  python -m climb        # 模組執行
"""

import os
import sys
from pathlib import Path

import paths

# PyInstaller 打包模式：設定 Playwright 瀏覽器路徑
if paths.is_frozen():
    pw_path = Path(sys._MEIPASS) / "ms-playwright"
    if pw_path.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(pw_path)

import customtkinter as ctk

# 預設深色主題
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

from gui.app import run


def main_gui():
    """GUI 啟動入口 — 供 pyproject.toml entry point 使用"""
    run()


if __name__ == "__main__":
    main_gui()
