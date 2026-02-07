"""
AI 批次處理頁籤
===============
掃描已擷取的文章，用 Claude API 進行分類、摘要、關鍵資訊提取。
"""

import os
import queue
import uuid

import customtkinter as ctk

import scraper
import ai_processor
from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_HEADING,
    PAD_X, PAD_Y, PAD_SECTION, PAD_INNER,
)
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.result_table import ResultTable


class AIProcessTab:
    """AI 批次處理頁籤"""

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent
        self.task_id = None

        self._articles: list[dict] = []
        self._checkboxes: list[tuple[ctk.BooleanVar, dict]] = []

        # 自己的 queue
        self._progress_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()

        self._build_ui()

    # ── UI 建構 ──────────────────────────────────────────────

    def _build_ui(self):
        # --- 來源目錄 ---
        dir_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        dir_frame.pack(fill="x", padx=PAD_X, pady=(PAD_Y, PAD_INNER))

        ctk.CTkLabel(
            dir_frame, text="文章目錄：", font=FONT_NORMAL,
        ).pack(side="left")

        self._dir_entry = ctk.CTkEntry(dir_frame, font=FONT_SMALL, width=350)
        self._dir_entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._dir_entry.insert(0, self.app.get_output_dir())

        ctk.CTkButton(
            dir_frame, text="瀏覽...", width=70, font=FONT_SMALL,
            command=self._browse_dir,
        ).pack(side="left", padx=(0, PAD_INNER))

        self._scan_btn = ctk.CTkButton(
            dir_frame, text="掃描文章", width=90, font=FONT_NORMAL,
            command=self._start_scan,
        )
        self._scan_btn.pack(side="left")

        # --- 掃描結果 / 費用估算 ---
        info_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        info_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        self._info_label = ctk.CTkLabel(
            info_frame, text="請點擊「掃描文章」開始",
            font=FONT_SMALL, anchor="w",
        )
        self._info_label.pack(side="left", fill="x", expand=True)

        self._cost_label = ctk.CTkLabel(
            info_frame, text="", font=FONT_SMALL, anchor="e",
        )
        self._cost_label.pack(side="right")

        # --- 篩選模式 ---
        filter_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        filter_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        self._filter_var = ctk.StringVar(value="unprocessed")
        ctk.CTkRadioButton(
            filter_frame, text="僅未處理", variable=self._filter_var,
            value="unprocessed", font=FONT_SMALL,
            command=self._apply_filter,
        ).pack(side="left", padx=(0, PAD_SECTION))
        ctk.CTkRadioButton(
            filter_frame, text="全部重新處理", variable=self._filter_var,
            value="all", font=FONT_SMALL,
            command=self._apply_filter,
        ).pack(side="left")

        # --- 文章列表 ---
        self._article_list = ctk.CTkScrollableFrame(
            self.parent, height=200,
        )
        self._article_list.pack(
            fill="both", expand=True, padx=PAD_X, pady=(0, PAD_INNER),
        )

        # 列表頂部按鈕
        list_btn_frame = ctk.CTkFrame(self._article_list, fg_color="transparent")
        list_btn_frame.pack(fill="x", pady=(0, PAD_INNER))

        ctk.CTkButton(
            list_btn_frame, text="全選", width=60, font=FONT_SMALL,
            command=lambda: self._set_all_checks(True),
        ).pack(side="left", padx=(0, PAD_INNER))

        ctk.CTkButton(
            list_btn_frame, text="取消全選", width=70, font=FONT_SMALL,
            fg_color="gray40", hover_color="gray30",
            command=lambda: self._set_all_checks(False),
        ).pack(side="left")

        self._list_container = ctk.CTkFrame(
            self._article_list, fg_color="transparent",
        )
        self._list_container.pack(fill="both", expand=True)

        # --- 操作按鈕 ---
        action_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        action_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        self._process_btn = ctk.CTkButton(
            action_frame, text="開始 AI 處理", width=140, font=FONT_NORMAL,
            command=self._start_processing, state="disabled",
        )
        self._process_btn.pack(side="left")

        self._model_label = ctk.CTkLabel(
            action_frame, text="", font=FONT_SMALL, anchor="w",
        )
        self._model_label.pack(side="left", padx=(PAD_SECTION, 0))

        # --- 進度面板 ---
        self._progress = ProgressPanel(
            self.parent, on_cancel=self._cancel_task,
        )

        # --- 結果表格 ---
        self._result_table = ResultTable(self.parent, height=150)
        self._result_table.pack(
            fill="both", expand=True, padx=PAD_X, pady=(PAD_INNER, 0),
        )
        self._result_table.pack_forget()

        # --- 統計 ---
        self._stats_label = ctk.CTkLabel(
            self.parent, text="", font=FONT_SMALL, anchor="w",
        )
        self._stats_label.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, PAD_Y))

    # ── 目錄瀏覽 ────────────────────────────────────────────

    def _browse_dir(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(
            initialdir=self._dir_entry.get(),
            title="選擇文章目錄",
        )
        if path:
            self._dir_entry.delete(0, "end")
            self._dir_entry.insert(0, path)

    # ── 掃描文章 ────────────────────────────────────────────

    def _start_scan(self):
        output_dir = self._dir_entry.get().strip()
        if not output_dir:
            self._info_label.configure(text="請先指定文章目錄")
            return

        self._scan_btn.configure(state="disabled")
        self._info_label.configure(text="掃描中...")

        self._articles = ai_processor.scan_articles(output_dir)
        self._populate_article_list()
        self._update_cost_estimate()
        self._scan_btn.configure(state="normal")

        total = len(self._articles)
        unprocessed = sum(1 for a in self._articles if not a["has_ai_data"])
        self._info_label.configure(
            text=f"找到 {total} 篇文章（{unprocessed} 篇未處理）"
        )

        # 檢查 API Key
        api_key = self._get_api_key()
        if not api_key:
            self._process_btn.configure(state="disabled")
            self._model_label.configure(
                text="請在設定頁填入 Anthropic API Key"
            )
        elif unprocessed == 0 and self._filter_var.get() == "unprocessed":
            self._process_btn.configure(state="disabled")
            self._model_label.configure(text="所有文章已處理完成")
        else:
            self._process_btn.configure(state="normal")
            model = self.app.config.get("ai_model", ai_processor.DEFAULT_MODEL)
            self._model_label.configure(text=f"模型：{model}")

    def _populate_article_list(self):
        """填充文章列表"""
        # 清除舊列表
        for widget in self._list_container.winfo_children():
            widget.destroy()
        self._checkboxes.clear()

        show_all = self._filter_var.get() == "all"

        for article in self._articles:
            if not show_all and article["has_ai_data"]:
                continue

            var = ctk.BooleanVar(value=not article["has_ai_data"])
            row = ctk.CTkFrame(self._list_container, fg_color="transparent")
            row.pack(fill="x", pady=1)

            cb = ctk.CTkCheckBox(
                row, text="", variable=var,
                checkbox_width=18, checkbox_height=18,
                width=20,
            )
            cb.pack(side="left", padx=(0, PAD_INNER))

            # 標題
            title = article["title"]
            if len(title) > 40:
                title = title[:37] + "..."
            ctk.CTkLabel(
                row, text=title, font=FONT_SMALL,
                width=300, anchor="w",
            ).pack(side="left", padx=(0, PAD_INNER))

            # 平台
            ctk.CTkLabel(
                row, text=article.get("platform", ""),
                font=FONT_SMALL, width=100, anchor="w",
            ).pack(side="left", padx=(0, PAD_INNER))

            # 狀態
            status = "✅ 已處理" if article["has_ai_data"] else "⬜ 未處理"
            ctk.CTkLabel(
                row, text=status, font=FONT_SMALL,
                width=80, anchor="w",
            ).pack(side="left")

            self._checkboxes.append((var, article))

    def _apply_filter(self):
        """篩選模式變更"""
        self._populate_article_list()
        self._update_cost_estimate()

    def _set_all_checks(self, value: bool):
        """全選/取消全選"""
        for var, _ in self._checkboxes:
            var.set(value)

    def _update_cost_estimate(self):
        """更新費用估算"""
        selected = self._get_selected_articles()
        if not selected:
            self._cost_label.configure(text="")
            return

        # 建構估算用的資料
        for a in selected:
            a.setdefault("has_ai_data", False)

        model = self.app.config.get("ai_model", ai_processor.DEFAULT_MODEL)
        cost = ai_processor.estimate_cost(selected, model)
        self._cost_label.configure(
            text=f"預估費用：~${cost['estimated_cost_usd']:.4f} USD"
        )

    def _get_selected_articles(self) -> list[dict]:
        """取得已勾選的文章"""
        return [article for var, article in self._checkboxes if var.get()]

    def _get_api_key(self) -> str:
        """取得 Anthropic API Key"""
        key = self.app.config.get("anthropic_api_key", "")
        if not key:
            key = os.environ.get("ANTHROPIC_API_KEY", "")
        return key

    # ── AI 處理 ─────────────────────────────────────────────

    def _start_processing(self):
        """開始 AI 批次處理"""
        selected = self._get_selected_articles()
        if not selected:
            self._info_label.configure(text="請至少選擇一篇文章")
            return

        api_key = self._get_api_key()
        if not api_key:
            self._info_label.configure(text="請先設定 Anthropic API Key")
            return

        model = self.app.config.get("ai_model", ai_processor.DEFAULT_MODEL)
        api_delay = float(self.app.config.get("ai_api_delay",
                                               ai_processor.DEFAULT_API_DELAY))

        # 清除舊結果
        self._result_table.clear()
        self._result_table.pack(
            fill="both", expand=True, padx=PAD_X, pady=(PAD_INNER, 0),
        )

        # 顯示進度面板
        self._progress.show()
        self._process_btn.configure(state="disabled")
        self._scan_btn.configure(state="disabled")

        # 提交背景任務
        self.task_id = f"ai_{uuid.uuid4().hex[:8]}"
        self.app.task_runner.submit(
            self.task_id,
            self._process_worker,
            selected, api_key, model, api_delay,
            progress_queue=self._progress_queue,
            result_queue=self._result_queue,
        )

    @staticmethod
    def _process_worker(articles, api_key, model, api_delay,
                        cancel_event, progress_queue, result_queue):
        """背景 AI 處理 worker"""
        total = len(articles)
        success_count = 0
        failed_count = 0

        for i, article in enumerate(articles, 1):
            if cancel_event.is_set():
                break

            title = article.get("title", "未知")
            path = article.get("path", "")
            progress_queue.put((i, total, f"正在處理：{title}"))

            try:
                # 讀取文章內容
                content_path = os.path.join(path, "content.md")
                with open(content_path, "r", encoding="utf-8") as f:
                    content = f.read()

                fm, body = ai_processor.parse_frontmatter(content)

                # 呼叫 Claude API
                ai_result = ai_processor.process_single_article(
                    body, api_key, model, title=title,
                )

                # 更新 frontmatter
                fm_updates = {
                    "category": (
                        f"{ai_result['category']}/{ai_result['subcategory']}"
                        if ai_result.get("subcategory")
                        else ai_result["category"]
                    ),
                    "tags": ai_result.get("tags", []),
                    "summary": ai_result.get("summary", ""),
                    "key_points": ai_result.get("key_points", []),
                    "clinical_relevance": ai_result.get("clinical_relevance", ""),
                }
                updated_content = ai_processor.update_frontmatter(
                    content, fm_updates,
                )

                with open(content_path, "w", encoding="utf-8") as f:
                    f.write(updated_content)

                # 更新 metadata.json
                import json
                from datetime import datetime
                meta_path = os.path.join(path, "metadata.json")
                if os.path.isfile(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                    except (json.JSONDecodeError, IOError):
                        meta = {}
                else:
                    meta = {}

                meta.update({
                    "category": fm_updates["category"],
                    "tags": ai_result.get("tags", []),
                    "summary": ai_result.get("summary", ""),
                    "ai_model": model,
                    "ai_processed_at": datetime.now().isoformat(),
                })
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                    f.write("\n")

                result_queue.put((title, "success", {
                    "category": fm_updates["category"],
                    "path": path,
                    "platform": article.get("platform", ""),
                }))
                success_count += 1

            except Exception as e:
                scraper.logger.error(f"[AI] {title}：{e}")
                result_queue.put((title, "failed", {
                    "error": str(e),
                    "path": path,
                    "platform": article.get("platform", ""),
                }))
                failed_count += 1

            # API 呼叫間隔
            if i < total and not cancel_event.is_set():
                import time
                time.sleep(api_delay)

        progress_queue.put((total, total, "AI 處理完成"))
        result_queue.put(("__AI_DONE__", "done", {
            "success": success_count,
            "failed": failed_count,
        }))

    def _cancel_task(self):
        """取消任務"""
        if self.task_id:
            self.app.task_runner.cancel(self.task_id)

    # ── Queue 輪詢 ──────────────────────────────────────────

    def poll_queues(self):
        """輪詢 progress 和 result queue"""
        # 進度
        for _ in range(10):
            try:
                current, total, msg = self._progress_queue.get_nowait()
                self._progress.update_progress(current, total, msg)
            except queue.Empty:
                break

        # 結果
        for _ in range(10):
            try:
                title, status, data = self._result_queue.get_nowait()
            except queue.Empty:
                break

            if title == "__AI_DONE__":
                self._on_batch_done(data)
                continue

            platform = data.get("platform", "")
            path = data.get("path", "")

            if status == "success":
                category = data.get("category", "")
                display = f"{title} → {category}"
            else:
                error = data.get("error", "")
                display = f"{title} (失敗：{error[:40]})"

            self._result_table.add_result(display, platform, status, path)

    def _on_batch_done(self, data: dict):
        """批次處理完成"""
        self._progress.set_complete()
        self._progress.set_status(
            f"完成！成功：{data.get('success', 0)}，"
            f"失敗：{data.get('failed', 0)}"
        )
        self._process_btn.configure(state="normal")
        self._scan_btn.configure(state="normal")
        self._stats_label.configure(
            text=self._result_table.get_stats_text(),
        )
        self.task_id = None
