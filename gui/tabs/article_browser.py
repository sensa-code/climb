"""
文章瀏覽器頁籤
===============
掃描輸出目錄，列出已擷取的文章，支援搜尋、篩選、預覽。
"""

import json
import os
import subprocess
import platform as plat

import customtkinter as ctk

import scraper
from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_HEADING, FONT_MONO_SMALL,
    PAD_X, PAD_Y, PAD_SECTION, PAD_INNER,
)


class ArticleBrowserTab:
    """文章瀏覽器頁籤"""

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent
        self._articles: list[dict] = []  # metadata 列表
        self._filtered: list[dict] = []
        self._selected_index: int = -1
        self._build_ui()

    def _build_ui(self):
        # --- 工具列 ---
        toolbar = ctk.CTkFrame(self.parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=PAD_X, pady=(PAD_Y, PAD_INNER))

        ctk.CTkLabel(toolbar, text="目錄：", font=FONT_SMALL).pack(side="left")

        self._dir_entry = ctk.CTkEntry(
            toolbar, font=FONT_SMALL, width=300,
        )
        self._dir_entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._dir_entry.insert(0, self.app.get_output_dir())

        ctk.CTkButton(
            toolbar, text="瀏覽", width=60, font=FONT_SMALL,
            command=self._browse_dir,
        ).pack(side="left", padx=(0, PAD_INNER))

        ctk.CTkButton(
            toolbar, text="重新整理", width=80, font=FONT_SMALL,
            command=self._refresh,
        ).pack(side="left", padx=(0, PAD_SECTION))

        self._count_label = ctk.CTkLabel(
            toolbar, text="共 0 篇", font=FONT_SMALL,
        )
        self._count_label.pack(side="left")

        # --- 搜尋和篩選 ---
        filter_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        filter_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        ctk.CTkLabel(filter_frame, text="搜尋：", font=FONT_SMALL).pack(side="left")

        self._search_entry = ctk.CTkEntry(
            filter_frame, font=FONT_SMALL, width=200,
            placeholder_text="標題關鍵字...",
        )
        self._search_entry.pack(side="left", padx=(PAD_INNER, PAD_SECTION))
        self._search_entry.bind("<KeyRelease>", self._on_search)

        ctk.CTkLabel(filter_frame, text="篩選：", font=FONT_SMALL).pack(side="left")

        self._filter_var = ctk.StringVar(value="全部")
        self._filter_menu = ctk.CTkOptionMenu(
            filter_frame,
            values=["全部"],
            variable=self._filter_var,
            command=self._on_filter_change,
            width=100, font=FONT_SMALL,
        )
        self._filter_menu.pack(side="left", padx=(PAD_INNER, 0))

        # --- 主要內容區（上下分割） ---
        content = ctk.CTkFrame(self.parent, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=PAD_X, pady=(0, PAD_Y))

        # 文章列表（上半）
        self._list_frame = ctk.CTkScrollableFrame(content, height=200)
        self._list_frame.pack(fill="both", expand=True, pady=(0, PAD_INNER))

        # 預覽區（下半）
        preview_container = ctk.CTkFrame(content)
        preview_container.pack(fill="both", expand=True)

        preview_header = ctk.CTkFrame(preview_container, fg_color="transparent")
        preview_header.pack(fill="x", padx=PAD_INNER, pady=(PAD_INNER, 0))

        ctk.CTkLabel(
            preview_header, text="預覽", font=FONT_HEADING,
        ).pack(side="left")

        self._open_btn = ctk.CTkButton(
            preview_header, text="開啟資料夾", width=90, font=FONT_SMALL,
            command=self._open_folder, state="disabled",
        )
        self._open_btn.pack(side="right", padx=(PAD_INNER, 0))

        self._preview_text = ctk.CTkTextbox(
            preview_container, font=FONT_MONO_SMALL,
            wrap="word", state="disabled",
        )
        self._preview_text.pack(fill="both", expand=True,
                                padx=PAD_INNER, pady=(PAD_INNER, PAD_INNER))

    def _browse_dir(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(
            initialdir=self._dir_entry.get(),
            title="選擇文章目錄",
        )
        if path:
            self._dir_entry.delete(0, "end")
            self._dir_entry.insert(0, path)
            self._refresh()

    def _refresh(self):
        """重新掃描目錄，載入文章元資料"""
        output_dir = os.path.expanduser(self._dir_entry.get().strip())
        self._articles.clear()

        if not os.path.isdir(output_dir):
            self._count_label.configure(text="目錄不存在")
            return

        # 掃描所有子目錄中的 metadata.json
        for entry in os.scandir(output_dir):
            if entry.is_dir():
                meta_path = os.path.join(entry.path, "metadata.json")
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        meta["_dir_path"] = entry.path
                        meta["_dir_name"] = entry.name
                        self._articles.append(meta)
                    except (json.JSONDecodeError, OSError):
                        pass

        # 按日期排序（最新在前）
        self._articles.sort(
            key=lambda a: a.get("date", ""),
            reverse=True,
        )

        # 更新平台篩選選項
        platforms = sorted(set(
            a.get("platform", "其他") for a in self._articles
        ))
        self._filter_menu.configure(values=["全部"] + platforms)
        self._filter_var.set("全部")

        self._apply_filter()
        self._count_label.configure(text=f"共 {len(self._articles)} 篇")

    def _apply_filter(self):
        """套用搜尋和篩選"""
        search_term = self._search_entry.get().strip().lower()
        platform_filter = self._filter_var.get()

        self._filtered = []
        for article in self._articles:
            # 平台篩選
            if platform_filter != "全部":
                if article.get("platform", "") != platform_filter:
                    continue

            # 搜尋篩選
            if search_term:
                title = article.get("title", "").lower()
                if search_term not in title:
                    continue

            self._filtered.append(article)

        self._render_list()

    def _render_list(self):
        """渲染文章列表"""
        # 清除舊列表
        for w in self._list_frame.winfo_children():
            w.destroy()

        if not self._filtered:
            ctk.CTkLabel(
                self._list_frame, text="（無符合條件的文章）",
                font=FONT_SMALL,
            ).pack(pady=PAD_SECTION)
            return

        # 表頭
        header = ctk.CTkFrame(self._list_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, PAD_INNER))

        for text, width in [("日期", 100), ("標題", 300), ("平台", 70), ("策略", 60)]:
            ctk.CTkLabel(
                header, text=text, font=FONT_SMALL,
                width=width, anchor="w",
            ).pack(side="left", padx=(0, PAD_INNER))

        # 文章列
        for idx, article in enumerate(self._filtered):
            row = ctk.CTkFrame(self._list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)

            date = article.get("date", "")[:10]
            title = article.get("title", "（無標題）")
            if len(title) > 40:
                title = title[:37] + "..."
            platform_name = article.get("platform", "")
            strategy = article.get("fetched_by", "")

            ctk.CTkLabel(row, text=date, font=FONT_SMALL, width=100, anchor="w").pack(
                side="left", padx=(0, PAD_INNER))

            title_btn = ctk.CTkButton(
                row, text=title, font=FONT_SMALL,
                width=300, anchor="w", fg_color="transparent",
                text_color=("#1a73e8", "#8ab4f8"),
                hover_color=("gray85", "gray25"),
                command=lambda i=idx: self._select_article(i),
            )
            title_btn.pack(side="left", padx=(0, PAD_INNER))

            ctk.CTkLabel(row, text=platform_name, font=FONT_SMALL, width=70, anchor="w").pack(
                side="left", padx=(0, PAD_INNER))

            ctk.CTkLabel(row, text=strategy, font=FONT_SMALL, width=60, anchor="w").pack(
                side="left")

    def _select_article(self, index: int):
        """選取文章，顯示預覽"""
        if index < 0 or index >= len(self._filtered):
            return

        self._selected_index = index
        article = self._filtered[index]

        # 讀取 content.md
        dir_path = article.get("_dir_path", "")
        content_path = os.path.join(dir_path, "content.md")

        preview_lines = []
        preview_lines.append(f"# {article.get('title', '（無標題）')}")
        preview_lines.append(f"來源：{article.get('source', '')}")
        preview_lines.append(f"擷取時間：{article.get('date', '')}")
        preview_lines.append(f"平台：{article.get('platform', '')}  策略：{article.get('fetched_by', '')}")
        preview_lines.append("─" * 40)

        if os.path.isfile(content_path):
            try:
                with open(content_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # 跳過 frontmatter
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        content = parts[2].strip()
                # 限制預覽長度
                if len(content) > 2000:
                    content = content[:2000] + "\n\n... (內容過長，已截斷)"
                preview_lines.append(content)
            except OSError:
                preview_lines.append("（無法讀取內容）")
        else:
            preview_lines.append("（content.md 不存在）")

        preview = "\n".join(preview_lines)

        self._preview_text.configure(state="normal")
        self._preview_text.delete("1.0", "end")
        self._preview_text.insert("1.0", preview)
        self._preview_text.configure(state="disabled")

        self._open_btn.configure(state="normal")

    def _open_folder(self):
        """開啟選取文章的資料夾"""
        if self._selected_index < 0:
            return
        article = self._filtered[self._selected_index]
        dir_path = article.get("_dir_path", "")
        if dir_path and os.path.isdir(dir_path):
            if plat.system() == "Windows":
                os.startfile(dir_path)
            elif plat.system() == "Darwin":
                subprocess.run(["open", dir_path])
            else:
                subprocess.run(["xdg-open", dir_path])

    def _on_search(self, event=None):
        """搜尋變更"""
        self._apply_filter()

    def _on_filter_change(self, choice: str):
        """篩選變更"""
        self._apply_filter()
