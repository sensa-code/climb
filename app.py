#!/usr/bin/env python3
"""
CLIMB GUI 啟動入口
===================
用法：python app.py
"""

import customtkinter as ctk

# 預設深色主題
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

from gui.app import run

if __name__ == "__main__":
    run()
