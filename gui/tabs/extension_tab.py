"""
Extension 伺服器頁籤
===================
控制本地 API Server 的啟停，顯示從 Chrome Extension 接收的文章紀錄，
並提供 Extension 安裝說明。
"""

import os
import queue
import subprocess
import platform as plat

import customtkinter as ctk

import scraper
from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_HEADING,
    PAD_X, PAD_Y, PAD_SECTION, PAD_INNER,
)
from gui.workers.api_server import ArticleAPIServer


class ExtensionTab:
    """Extension 伺服器控制頁籤"""

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent

        # 接收文章紀錄的 queue
        self._log_queue: queue.Queue = queue.Queue()

        # API Server 實例
        port = self.app.config.get("extension_server_port", 3456)
        self._server = ArticleAPIServer(
            port=port,
            output_dir=self.app.get_output_dir(),
            log_queue=self._log_queue,
        )

        self._build_ui()

        # 自動啟動
        if self.app.config.get("extension_server_auto_start", False):
            self._toggle_server()

    def _build_ui(self):
        # === 伺服器控制區 ===
        server_frame = ctk.CTkFrame(self.parent)
        server_frame.pack(fill="x", padx=PAD_X, pady=(PAD_Y, PAD_INNER))

        ctk.CTkLabel(
            server_frame, text="Extension API Server",
            font=FONT_HEADING, anchor="w",
        ).pack(fill="x", padx=PAD_INNER, pady=(PAD_INNER, PAD_INNER))

        # 狀態列
        status_row = ctk.CTkFrame(server_frame, fg_color="transparent")
        status_row.pack(fill="x", padx=PAD_INNER, pady=(0, PAD_INNER))

        self._status_label = ctk.CTkLabel(
            status_row, text="狀態：已停止",
            font=FONT_NORMAL, anchor="w",
        )
        self._status_label.pack(side="left")

        self._toggle_btn = ctk.CTkButton(
            status_row, text="啟動伺服器", width=110,
            font=FONT_NORMAL, command=self._toggle_server,
        )
        self._toggle_btn.pack(side="right")

        # Port + 輸出目錄
        config_row = ctk.CTkFrame(server_frame, fg_color="transparent")
        config_row.pack(fill="x", padx=PAD_INNER, pady=(0, PAD_INNER))

        ctk.CTkLabel(config_row, text="Port：", font=FONT_SMALL).pack(side="left")

        self._port_entry = ctk.CTkEntry(
            config_row, font=FONT_SMALL, width=70,
        )
        self._port_entry.pack(side="left", padx=(PAD_INNER, PAD_SECTION))
        self._port_entry.insert(0, str(self._server.port))

        ctk.CTkLabel(
            config_row, text="輸出目錄：", font=FONT_SMALL,
        ).pack(side="left")

        self._output_entry = ctk.CTkEntry(
            config_row, font=FONT_SMALL, width=250,
        )
        self._output_entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._output_entry.insert(0, self.app.get_output_dir())

        ctk.CTkButton(
            config_row, text="瀏覽...", width=70, font=FONT_SMALL,
            command=self._browse_output,
        ).pack(side="left")

        # 自動啟動勾選框
        auto_row = ctk.CTkFrame(server_frame, fg_color="transparent")
        auto_row.pack(fill="x", padx=PAD_INNER, pady=(0, PAD_INNER))

        self._auto_start_var = ctk.BooleanVar(
            value=self.app.config.get("extension_server_auto_start", False)
        )
        ctk.CTkCheckBox(
            auto_row, text="啟動 GUI 時自動開啟伺服器",
            variable=self._auto_start_var, font=FONT_SMALL,
            checkbox_width=18, checkbox_height=18,
            command=self._save_auto_start_setting,
        ).pack(side="left")

        # === 已接收文章紀錄 ===
        log_frame = ctk.CTkFrame(self.parent)
        log_frame.pack(fill="both", expand=True, padx=PAD_X, pady=(0, PAD_INNER))

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=PAD_INNER, pady=(PAD_INNER, PAD_INNER))

        ctk.CTkLabel(
            log_header, text="已接收文章",
            font=FONT_HEADING, anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            log_header, text="清除紀錄", width=80, font=FONT_SMALL,
            command=self._clear_log,
        ).pack(side="right")

        self._log_textbox = ctk.CTkTextbox(
            log_frame, font=FONT_SMALL, state="disabled",
        )
        self._log_textbox.pack(
            fill="both", expand=True, padx=PAD_INNER, pady=(0, PAD_INNER),
        )

        # === Chrome Extension 安裝說明 ===
        install_frame = ctk.CTkFrame(self.parent)
        install_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_Y))

        ctk.CTkLabel(
            install_frame, text="Chrome Extension 安裝說明",
            font=FONT_HEADING, anchor="w",
        ).pack(fill="x", padx=PAD_INNER, pady=(PAD_INNER, PAD_INNER))

        instructions = (
            "1. 開啟 Chrome → 在網址列輸入 chrome://extensions\n"
            "2. 開啟右上角「開發人員模式」開關\n"
            "3. 點擊「載入未封裝項目」\n"
            "4. 選擇下方的 Extension 資料夾路徑"
        )
        ctk.CTkLabel(
            install_frame, text=instructions,
            font=FONT_SMALL, anchor="w", justify="left",
        ).pack(fill="x", padx=PAD_INNER, pady=(0, PAD_INNER))

        btn_row = ctk.CTkFrame(install_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=PAD_INNER, pady=(0, PAD_INNER))

        ctk.CTkButton(
            btn_row, text="複製 Extension 路徑", width=140,
            font=FONT_SMALL, command=self._copy_extension_path,
        ).pack(side="left", padx=(0, PAD_INNER))

        ctk.CTkButton(
            btn_row, text="開啟 Extension 資料夾", width=150,
            font=FONT_SMALL, command=self._open_extension_folder,
        ).pack(side="left")

    def poll_queues(self):
        """輪詢 log_queue（由主視窗呼叫）"""
        for _ in range(50):
            try:
                entry = self._log_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self._append_log_entry(entry)
            except Exception:
                pass

    def _toggle_server(self):
        """啟動或停止伺服器"""
        if self._server.is_running():
            self._server.stop()
            self._status_label.configure(text="狀態：已停止")
            self._toggle_btn.configure(text="啟動伺服器")
            self._port_entry.configure(state="normal")
        else:
            # 讀取 port 和 output_dir
            try:
                port = int(self._port_entry.get().strip())
            except ValueError:
                port = 3456
            output_dir = self._output_entry.get().strip() or self.app.get_output_dir()

            self._server.port = port
            self._server.output_dir = output_dir

            success, msg = self._server.start()
            if success:
                self._status_label.configure(
                    text=f"狀態：運行中 (port {port})"
                )
                self._toggle_btn.configure(text="停止伺服器")
                self._port_entry.configure(state="disabled")
            else:
                from tkinter import messagebox
                messagebox.showerror("啟動失敗", msg)

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
            if self._server.is_running():
                self._server.update_output_dir(path)

    def _save_auto_start_setting(self):
        """儲存自動啟動設定到 config"""
        self.app.config["extension_server_auto_start"] = self._auto_start_var.get()
        try:
            port = int(self._port_entry.get().strip())
        except ValueError:
            port = 3456
        self.app.config["extension_server_port"] = port

        # 寫入 config.json
        import paths
        config_path = str(paths.get_config_path())
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = __import__("json").load(f)
            config["extension_server_auto_start"] = self._auto_start_var.get()
            config["extension_server_port"] = port
            with open(config_path, "w", encoding="utf-8") as f:
                __import__("json").dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            scraper.logger.warning(f"儲存設定失敗：{e}")

    def _append_log_entry(self, entry: dict):
        """新增一筆文章接收紀錄到日誌"""
        time_str = entry.get("time", "")
        platform = entry.get("platform", "")
        title = entry.get("title", "")
        status = entry.get("status", "")

        icon = "✅" if status == "success" else "❌"
        line = f"{time_str}  {platform:10s}  {icon}  {title}\n"

        self._log_textbox.configure(state="normal")
        self._log_textbox.insert("end", line)
        self._log_textbox.see("end")
        self._log_textbox.configure(state="disabled")

    def _clear_log(self):
        """清除接收紀錄"""
        self._log_textbox.configure(state="normal")
        self._log_textbox.delete("1.0", "end")
        self._log_textbox.configure(state="disabled")

    def _get_extension_path(self) -> str:
        """取得 Extension 資料夾路徑"""
        import paths
        return str(paths.get_extension_dir())

    def _copy_extension_path(self):
        """複製 Extension 路徑到剪貼簿"""
        path = self._get_extension_path()
        self.parent.clipboard_clear()
        self.parent.clipboard_append(path)

    def _open_extension_folder(self):
        """開啟 Extension 資料夾"""
        path = self._get_extension_path()
        if os.path.exists(path):
            if plat.system() == "Windows":
                os.startfile(path)
            elif plat.system() == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        else:
            from tkinter import messagebox
            messagebox.showwarning(
                "資料夾不存在",
                f"Extension 資料夾不存在：\n{path}\n\n請確認專案結構完整。"
            )

    def shutdown(self):
        """關閉伺服器（由主視窗呼叫）"""
        if self._server.is_running():
            self._server.stop()
