"""
路徑解析模組
==============
統一處理開發模式與 PyInstaller 打包模式的路徑差異。

開發模式：所有資源在原始碼目錄
打包模式：
  - 唯讀資源（bundled）→ sys._MEIPASS（PyInstaller 解壓目錄）
  - 可寫檔案（config, output）→ exe 所在目錄
"""

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """是否在 PyInstaller 打包模式下執行"""
    return getattr(sys, "frozen", False)


def get_bundle_dir() -> Path:
    """取得唯讀資源目錄（bundled 的 extension/、預設 config 等）。

    開發模式：專案根目錄（paths.py 所在位置）
    打包模式：sys._MEIPASS（PyInstaller 解壓暫存目錄）
    """
    if is_frozen():
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def get_app_dir() -> Path:
    """取得可寫的應用程式目錄（config.json、logs 等）。

    開發模式：專案根目錄
    打包模式：exe 所在目錄
    """
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).parent


def get_config_path() -> Path:
    """取得 config.json 路徑（可寫）。

    首次啟動打包版時，從 bundle 複製預設 config.json 到 exe 旁。
    """
    user_config = get_app_dir() / "config.json"
    if not user_config.exists():
        default_config = get_bundle_dir() / "config.json"
        if default_config.exists():
            import shutil
            shutil.copy2(default_config, user_config)
    return user_config


def get_extension_dir() -> Path:
    """取得 Chrome Extension 資料夾路徑（唯讀）。

    開發模式：專案根目錄下的 extension/
    打包模式：PyInstaller bundle 中的 extension/
    """
    return get_bundle_dir() / "extension"
