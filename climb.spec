# -*- mode: python ; coding: utf-8 -*-
"""
CLIMB PyInstaller 打包規格
============================
用法：pyinstaller climb.spec --clean

產出：dist/CLIMB.exe（單一執行檔，含 Playwright Chromium）
"""

import os
import sys
import glob

block_cipher = None

# ============================================================
# 找到 Playwright Chromium 瀏覽器
# ============================================================

pw_browsers_path = os.path.expanduser("~/AppData/Local/ms-playwright")
chromium_dirs = sorted(glob.glob(os.path.join(pw_browsers_path, "chromium-*")))

pw_datas = []
if chromium_dirs:
    chromium_dir = chromium_dirs[-1]  # 取最新版本
    chromium_name = os.path.basename(chromium_dir)
    pw_datas.append((chromium_dir, os.path.join("ms-playwright", chromium_name)))
    print(f"[CLIMB] 打包 Playwright Chromium: {chromium_dir}")
else:
    print("[CLIMB] ⚠️ 找不到 Playwright Chromium！請先執行 playwright install chromium")

# ============================================================
# Analysis — 掃描所有依賴
# ============================================================

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("config.json", "."),                    # 預設設定檔
        ("extension", "extension"),              # Chrome Extension 完整目錄
    ] + pw_datas,
    hiddenimports=[
        # 核心模組（root level .py，PyInstaller 可能不會自動偵測）
        "paths",
        "scraper",
        "ai_processor",
        # GUI 框架
        "customtkinter",
        # Claude API
        "anthropic",
        "anthropic._exceptions",
        # Playwright
        "playwright",
        "playwright.sync_api",
        "playwright._impl",
        # HTML 處理
        "markdownify",
        "yaml",
        # GUI 子模組（延遲 import，PyInstaller 掃不到）
        "gui",
        "gui.app",
        "gui.theme",
        "gui.tabs",
        "gui.tabs.single_fetch",
        "gui.tabs.batch_fetch",
        "gui.tabs.ptt_board",
        "gui.tabs.extension_tab",
        "gui.tabs.ai_process",
        "gui.tabs.settings",
        "gui.tabs.article_browser",
        "gui.tabs.log_viewer",
        "gui.widgets",
        "gui.widgets.url_input",
        "gui.widgets.progress_panel",
        "gui.widgets.result_table",
        "gui.workers",
        "gui.workers.task_runner",
        "gui.workers.log_handler",
        "gui.workers.api_server",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的大型套件以減小體積
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "PIL",
        "tkinter.test",
        "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ============================================================
# PYZ — 壓縮 Python 模組
# ============================================================

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ============================================================
# EXE — 建構執行檔
# ============================================================

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CLIMB",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                   # 啟用 UPX 壓縮
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # 隱藏終端視窗（純 GUI）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                  # 未來可加入 .ico 圖示
)
