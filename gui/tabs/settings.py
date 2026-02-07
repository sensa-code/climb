"""
設定頁籤
=========
管理 config.json 設定值，支援儲存、重設。
儲存後熱載入到 scraper 模組全域變數。
"""

import json
import os

import customtkinter as ctk

import scraper
from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_HEADING,
    PAD_X, PAD_Y, PAD_SECTION, PAD_INNER,
)


class SettingsTab:
    """設定頁籤"""

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent
        self._entries: dict[str, ctk.CTkEntry] = {}
        self._build_ui()
        self._load_current_values()

    def _build_ui(self):
        # 外層可捲動容器
        scroll = ctk.CTkScrollableFrame(self.parent)
        scroll.pack(fill="both", expand=True, padx=PAD_X, pady=PAD_Y)

        # --- 輸出設定 ---
        self._add_section(scroll, "輸出")
        self._add_dir_field(scroll, "output_dir", "預設輸出目錄")

        # --- 網路設定 ---
        self._add_section(scroll, "網路")
        self._add_number_field(scroll, "request_timeout", "請求逾時（秒）")
        self._add_number_field(scroll, "max_retries", "最大重試次數")
        self._add_number_field(scroll, "retry_base_delay", "重試基本延遲（秒）")
        self._add_number_field(scroll, "politeness_delay", "禮貌延遲（秒）")

        # --- Jina Reader ---
        self._add_section(scroll, "Jina Reader")
        self._add_text_field(scroll, "jina_base_url", "Jina 基本 URL")
        self._add_secret_field(scroll, "jina_api_key", "Jina API Key")

        # --- Playwright ---
        self._add_section(scroll, "Playwright")

        pw_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        pw_frame.pack(fill="x", pady=(0, PAD_INNER))

        self._pw_status_label = ctk.CTkLabel(
            pw_frame, text="檢查中...", font=FONT_SMALL, anchor="w",
        )
        self._pw_status_label.pack(side="left", fill="x", expand=True)

        self._pw_install_btn = ctk.CTkButton(
            pw_frame, text="安裝 Chromium", width=120, font=FONT_SMALL,
            command=self._install_playwright,
        )
        self._pw_install_btn.pack(side="right", padx=(PAD_INNER, 0))

        ctk.CTkButton(
            pw_frame, text="檢查狀態", width=80, font=FONT_SMALL,
            fg_color="gray40", hover_color="gray30",
            command=self._check_playwright_status,
        ).pack(side="right")

        # 初始檢查 Playwright 狀態
        self.parent.after(200, self._check_playwright_status)

        # --- 日誌 ---
        self._add_section(scroll, "日誌")

        log_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        log_frame.pack(fill="x", pady=(0, PAD_INNER))

        ctk.CTkLabel(log_frame, text="日誌等級：", font=FONT_SMALL).pack(side="left")

        self._log_level_var = ctk.StringVar(value="INFO")
        ctk.CTkOptionMenu(
            log_frame,
            values=["DEBUG", "INFO", "WARNING", "ERROR"],
            variable=self._log_level_var,
            width=120, font=FONT_SMALL,
        ).pack(side="left", padx=(PAD_INNER, 0))

        # --- 外觀 ---
        self._add_section(scroll, "外觀")

        appearance_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        appearance_frame.pack(fill="x", pady=(0, PAD_INNER))

        ctk.CTkLabel(appearance_frame, text="主題：", font=FONT_SMALL).pack(side="left")

        self._theme_var = ctk.StringVar(value="dark")
        for text, value in [("深色", "dark"), ("淺色", "light"), ("系統", "system")]:
            ctk.CTkRadioButton(
                appearance_frame, text=text, variable=self._theme_var,
                value=value, font=FONT_SMALL,
                command=self._on_theme_change,
            ).pack(side="left", padx=(PAD_INNER, PAD_SECTION))

        # --- 按鈕列 ---
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(PAD_SECTION, 0))

        ctk.CTkButton(
            btn_frame, text="儲存設定", width=120, font=FONT_NORMAL,
            command=self._save_settings,
        ).pack(side="left", padx=(0, PAD_INNER))

        ctk.CTkButton(
            btn_frame, text="重設為預設值", width=120, font=FONT_NORMAL,
            fg_color="gray40", hover_color="gray30",
            command=self._reset_defaults,
        ).pack(side="left")

        # 狀態訊息
        self._status_label = ctk.CTkLabel(
            btn_frame, text="", font=FONT_SMALL, anchor="w",
        )
        self._status_label.pack(side="left", padx=(PAD_SECTION, 0))

    def _add_section(self, parent, title: str):
        """新增區塊標題"""
        ctk.CTkLabel(
            parent, text=title, font=FONT_HEADING, anchor="w",
        ).pack(fill="x", pady=(PAD_SECTION, PAD_INNER))

    def _add_text_field(self, parent, key: str, label: str, width: int = 400):
        """新增文字欄位"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(0, PAD_INNER))

        ctk.CTkLabel(frame, text=f"{label}：", font=FONT_SMALL, width=160, anchor="w").pack(side="left")

        entry = ctk.CTkEntry(frame, font=FONT_SMALL, width=width)
        entry.pack(side="left", padx=(PAD_INNER, 0))
        self._entries[key] = entry

    def _add_number_field(self, parent, key: str, label: str):
        """新增數字欄位"""
        self._add_text_field(parent, key, label, width=100)

    def _add_dir_field(self, parent, key: str, label: str):
        """新增目錄選擇欄位"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(0, PAD_INNER))

        ctk.CTkLabel(frame, text=f"{label}：", font=FONT_SMALL, width=160, anchor="w").pack(side="left")

        entry = ctk.CTkEntry(frame, font=FONT_SMALL, width=350)
        entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._entries[key] = entry

        ctk.CTkButton(
            frame, text="瀏覽...", width=70, font=FONT_SMALL,
            command=lambda: self._browse_dir(key),
        ).pack(side="left")

    def _add_secret_field(self, parent, key: str, label: str):
        """新增密碼欄位"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=(0, PAD_INNER))

        ctk.CTkLabel(frame, text=f"{label}：", font=FONT_SMALL, width=160, anchor="w").pack(side="left")

        entry = ctk.CTkEntry(frame, font=FONT_SMALL, width=300, show="●")
        entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._entries[key] = entry

        show_var = ctk.BooleanVar(value=False)

        def toggle_show():
            entry.configure(show="" if show_var.get() else "●")

        ctk.CTkCheckBox(
            frame, text="顯示", variable=show_var,
            command=toggle_show, font=FONT_SMALL,
            checkbox_width=18, checkbox_height=18,
        ).pack(side="left")

    def _browse_dir(self, key: str):
        """瀏覽目錄"""
        from tkinter import filedialog
        entry = self._entries[key]
        path = filedialog.askdirectory(
            initialdir=entry.get(),
            title="選擇目錄",
        )
        if path:
            entry.delete(0, "end")
            entry.insert(0, path)

    def _load_current_values(self):
        """載入目前的設定值"""
        config = self.app.config

        field_map = {
            "output_dir": config.get("output_dir", scraper.DEFAULT_OUTPUT_DIR),
            "request_timeout": str(config.get("request_timeout", scraper.REQUEST_TIMEOUT)),
            "max_retries": str(config.get("max_retries", scraper.MAX_RETRIES)),
            "retry_base_delay": str(config.get("retry_base_delay", scraper.RETRY_BASE_DELAY)),
            "politeness_delay": str(config.get("politeness_delay", scraper.POLITENESS_DELAY)),
            "jina_base_url": config.get("jina_base_url", scraper.JINA_BASE_URL),
            "jina_api_key": scraper.JINA_API_KEY,
        }

        for key, value in field_map.items():
            entry = self._entries.get(key)
            if entry:
                entry.delete(0, "end")
                entry.insert(0, value)

        self._log_level_var.set(config.get("log_level", "INFO"))

    def _save_settings(self):
        """儲存設定到 config.json 並熱載入"""
        try:
            # 收集值
            new_config = {
                "output_dir": self._entries["output_dir"].get().strip(),
                "request_timeout": int(self._entries["request_timeout"].get()),
                "max_retries": int(self._entries["max_retries"].get()),
                "retry_base_delay": int(self._entries["retry_base_delay"].get()),
                "politeness_delay": int(self._entries["politeness_delay"].get()),
                "jina_base_url": self._entries["jina_base_url"].get().strip(),
                "log_level": self._log_level_var.get(),
            }

            # 驗證數值
            for key in ("request_timeout", "max_retries", "retry_base_delay", "politeness_delay"):
                if new_config[key] < 0:
                    raise ValueError(f"{key} 不能為負數")

            # 寫入 config.json
            config_path = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "..", "config.json")
            config_path = os.path.normpath(config_path)

            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, ensure_ascii=False, indent=2)
                f.write("\n")

            # 熱載入到 scraper 模組全域變數
            scraper.DEFAULT_OUTPUT_DIR = os.path.expanduser(new_config["output_dir"])
            scraper.REQUEST_TIMEOUT = new_config["request_timeout"]
            scraper.MAX_RETRIES = new_config["max_retries"]
            scraper.RETRY_BASE_DELAY = new_config["retry_base_delay"]
            scraper.POLITENESS_DELAY = new_config["politeness_delay"]
            scraper.JINA_BASE_URL = new_config["jina_base_url"]

            # 更新 Jina API Key（如果有填）
            jina_key = self._entries["jina_api_key"].get().strip()
            if jina_key:
                scraper.JINA_API_KEY = jina_key

            # 更新日誌等級
            scraper.logger.setLevel(getattr(
                __import__("logging"), new_config["log_level"], 20
            ))

            # 更新 app 共享設定
            self.app.config.update(new_config)

            self._status_label.configure(text="✅ 設定已儲存", text_color="green")

        except (ValueError, TypeError) as e:
            self._status_label.configure(text=f"❌ 輸入錯誤：{e}", text_color="red")
        except Exception as e:
            self._status_label.configure(text=f"❌ 儲存失敗：{e}", text_color="red")

    def _reset_defaults(self):
        """重設為預設值"""
        for key, value in scraper._DEFAULTS.items():
            entry = self._entries.get(key)
            if entry:
                entry.delete(0, "end")
                entry.insert(0, str(value))

        self._log_level_var.set("INFO")
        self._status_label.configure(text="已重設為預設值", text_color="gray")

    def _on_theme_change(self):
        """主題變更"""
        ctk.set_appearance_mode(self._theme_var.get())

    # --- Playwright 管理 ---

    def _check_playwright_status(self):
        """檢查 Playwright 安裝狀態並更新 UI"""
        import threading

        def _worker():
            status = scraper.check_playwright_status()
            self.parent.after(0, lambda: self._update_pw_ui(status))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_pw_ui(self, status: dict):
        """根據狀態更新 Playwright UI 元件"""
        if not status["installed"]:
            text = "❌ 未安裝 — 請先執行 pip install playwright"
            self._pw_install_btn.configure(state="disabled")
        elif not status["browsers_ready"]:
            text = "⚠️ 已安裝，但 Chromium 瀏覽器未下載"
            self._pw_install_btn.configure(state="normal")
        else:
            text = "✅ 已安裝，Chromium 就緒"
            self._pw_install_btn.configure(state="disabled")
        self._pw_status_label.configure(text=f"狀態：{text}")

    def _install_playwright(self):
        """背景安裝 Playwright Chromium"""
        import threading

        self._pw_install_btn.configure(state="disabled")
        self._pw_status_label.configure(text="狀態：正在安裝 Chromium（可能需要幾分鐘）...")

        def _worker():
            success, msg = scraper.install_playwright_browsers()
            self.parent.after(0, lambda: self._on_pw_install_done(success, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_pw_install_done(self, success: bool, msg: str):
        """Playwright 安裝完成回調"""
        if success:
            self._pw_status_label.configure(text="狀態：✅ Chromium 安裝成功！")
        else:
            self._pw_status_label.configure(
                text=f"狀態：❌ 安裝失敗 — {msg[:80]}"
            )
        self._check_playwright_status()
