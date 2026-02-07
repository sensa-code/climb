"""
PTT 看板頁籤
=============
兩階段操作：掃描看板取得文章列表 → 選取文章 → 擷取。
"""

import os
import queue
import time
import uuid

import customtkinter as ctk

import scraper
from gui.theme import (
    FONT_NORMAL, FONT_SMALL, FONT_HEADING,
    PAD_X, PAD_Y, PAD_SECTION, PAD_INNER,
)
from gui.widgets.progress_panel import ProgressPanel
from gui.widgets.result_table import ResultTable


# PTT 獸醫相關常用看板
COMMON_BOARDS = ["cat", "dog", "AnimalPark", "Vet", "Veterinary", "PetBird"]


class PttBoardTab:
    """PTT 看板頁籤"""

    def __init__(self, parent: ctk.CTkFrame, app):
        self.app = app
        self.parent = parent
        self.task_id = None
        self._article_urls: list[str] = []
        self._checkboxes: list[tuple[ctk.BooleanVar, str, str]] = []

        # 自己的 queue
        self._progress_queue: queue.Queue = queue.Queue()
        self._result_queue: queue.Queue = queue.Queue()

        self._build_ui()

    def _build_ui(self):
        # --- 看板選擇 ---
        board_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        board_frame.pack(fill="x", padx=PAD_X, pady=(PAD_Y, PAD_INNER))

        ctk.CTkLabel(board_frame, text="看板：", font=FONT_NORMAL).pack(side="left")

        self._board_var = ctk.StringVar(value="cat")
        self._board_menu = ctk.CTkComboBox(
            board_frame, values=COMMON_BOARDS,
            variable=self._board_var, font=FONT_SMALL, width=150,
        )
        self._board_menu.pack(side="left", padx=(PAD_INNER, PAD_SECTION))

        ctk.CTkLabel(board_frame, text="頁數：", font=FONT_NORMAL).pack(side="left")

        self._pages_var = ctk.StringVar(value="3")
        self._pages_entry = ctk.CTkEntry(
            board_frame, textvariable=self._pages_var,
            font=FONT_SMALL, width=60,
        )
        self._pages_entry.pack(side="left", padx=(PAD_INNER, PAD_SECTION))

        self._scan_btn = ctk.CTkButton(
            board_frame, text="掃描看板", width=100, font=FONT_NORMAL,
            command=self._start_scan,
        )
        self._scan_btn.pack(side="left")

        # --- 輸出目錄 ---
        output_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        output_frame.pack(fill="x", padx=PAD_X, pady=(0, PAD_INNER))

        ctk.CTkLabel(output_frame, text="輸出目錄：", font=FONT_SMALL).pack(side="left")

        self._output_entry = ctk.CTkEntry(
            output_frame, font=FONT_SMALL, width=300,
        )
        self._output_entry.pack(side="left", padx=(PAD_INNER, PAD_INNER))
        self._output_entry.insert(0, self.app.get_output_dir())

        ctk.CTkButton(
            output_frame, text="瀏覽...", width=70, font=FONT_SMALL,
            command=self._browse_output,
        ).pack(side="left")

        # --- 掃描結果（文章列表） ---
        self._scan_result_label = ctk.CTkLabel(
            self.parent, text="", font=FONT_SMALL, anchor="w",
        )

        self._articles_frame = ctk.CTkScrollableFrame(self.parent, height=200)

        # 選取控制列
        self._select_frame = ctk.CTkFrame(self.parent, fg_color="transparent")

        ctk.CTkButton(
            self._select_frame, text="全選", width=60, font=FONT_SMALL,
            command=self._select_all,
        ).pack(side="left", padx=(0, PAD_INNER))

        ctk.CTkButton(
            self._select_frame, text="全不選", width=70, font=FONT_SMALL,
            command=self._deselect_all,
        ).pack(side="left", padx=(0, PAD_SECTION))

        self._fetch_selected_btn = ctk.CTkButton(
            self._select_frame, text="開始擷取選取的文章", width=160,
            font=FONT_NORMAL, command=self._start_fetch_selected,
        )
        self._fetch_selected_btn.pack(side="right")

        # --- 進度面板 ---
        self._progress = ProgressPanel(
            self.parent,
            on_cancel=self._cancel_task,
        )

        # --- 結果表格 ---
        self._result_table = ResultTable(self.parent, height=150)

        self._stats_label = ctk.CTkLabel(
            self.parent, text="", font=FONT_SMALL, anchor="w",
        )

    def poll_queues(self):
        """輪詢自己的 queue（由主視窗呼叫）"""
        # 進度
        try:
            while True:
                current, total, message = self._progress_queue.get_nowait()
                self._progress.update_progress(current, total, message)
        except queue.Empty:
            pass

        # 結果
        try:
            while True:
                url, status, data = self._result_queue.get_nowait()
                self._on_result(url, status, data)
        except queue.Empty:
            pass

    def _browse_output(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(
            initialdir=self._output_entry.get(),
            title="選擇輸出目錄",
        )
        if path:
            self._output_entry.delete(0, "end")
            self._output_entry.insert(0, path)

    def _start_scan(self):
        """開始掃描看板"""
        board = self._board_var.get().strip()
        if not board:
            return

        try:
            pages = int(self._pages_var.get())
        except ValueError:
            pages = 3

        self.task_id = f"ptt_scan_{uuid.uuid4().hex[:8]}"
        self._scan_btn.configure(state="disabled")
        self._progress.show()

        # 清除舊結果
        self._clear_scan_results()

        output_dir = self._output_entry.get().strip() or self.app.get_output_dir()

        self.app.task_runner.submit(
            self.task_id,
            self._scan_worker,
            board, pages, output_dir,
            progress_queue=self._progress_queue,
            result_queue=self._result_queue,
        )

    @staticmethod
    def _scan_worker(board, pages, output_dir, cancel_event, progress_queue, result_queue):
        """背景掃描 PTT 看板"""
        try:
            progress_queue.put((1, 2, f"正在掃描 PTT {board} 看板..."))

            import requests as req
            from bs4 import BeautifulSoup

            base_url = "https://www.ptt.cc"
            board_url = f"{base_url}/bbs/{board}/index.html"

            # 使用 Session 維持連線，避免 ConnectionResetError
            session = req.Session()
            session.cookies.set("over18", "1")
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Referer': 'https://www.ptt.cc/',
            })

            article_urls = []
            article_titles = []
            current_url = board_url

            for page_num in range(pages):
                if cancel_event.is_set():
                    break

                progress_queue.put((page_num + 1, pages + 1,
                                    f"掃描第 {page_num + 1}/{pages} 頁..."))

                # 重試機制（最多 3 次）
                resp = None
                for attempt in range(3):
                    try:
                        resp = session.get(
                            current_url, timeout=scraper.REQUEST_TIMEOUT,
                        )
                        resp.raise_for_status()
                        break
                    except (req.ConnectionError, req.Timeout) as e:
                        if attempt < 2:
                            scraper.logger.warning(
                                f"PTT 連線失敗（第 {attempt + 1} 次），{2 ** attempt} 秒後重試..."
                            )
                            time.sleep(2 ** attempt)
                        else:
                            raise

                soup = BeautifulSoup(resp.text, "html.parser")

                # 取得文章列表
                for div in soup.select("div.r-ent"):
                    title_tag = div.select_one("div.title a")
                    if title_tag:
                        href = title_tag.get("href", "")
                        title = title_tag.get_text(strip=True)
                        full_url = base_url + href
                        article_urls.append(full_url)
                        article_titles.append(title)

                # 找上一頁連結
                prev_link = None
                for a in soup.select("div.btn-group-paging a"):
                    if "上頁" in a.get_text():
                        prev_link = a
                        break

                if prev_link:
                    current_url = base_url + prev_link["href"]
                else:
                    break

                # 頁與頁之間禮貌延遲
                if page_num < pages - 1:
                    time.sleep(1)

            session.close()

            # 過濾已擷取的
            new_urls = []
            new_titles = []
            for url, title in zip(article_urls, article_titles):
                if not scraper.is_already_fetched(url, output_dir):
                    new_urls.append(url)
                    new_titles.append(title)

            progress_queue.put((pages + 1, pages + 1, "掃描完成"))
            result_queue.put(("__SCAN_DONE__", "done", {
                "urls": new_urls,
                "titles": new_titles,
                "total_found": len(article_urls),
                "new_count": len(new_urls),
            }))

        except Exception as e:
            scraper.logger.error(f"掃描 PTT 看板失敗：{e}")
            result_queue.put(("__SCAN_DONE__", "failed", {"error": str(e)}))

    def _on_result(self, url, status, data):
        """處理結果"""
        if url == "__SCAN_DONE__":
            self._scan_btn.configure(state="normal")
            self._progress.set_complete()

            if status == "failed":
                error = data.get("error", "未知錯誤")
                self._scan_result_label.configure(text=f"掃描失敗：{error}")
                self._scan_result_label.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, 0))
                return

            urls = data.get("urls", [])
            titles = data.get("titles", [])
            total = data.get("total_found", 0)
            new_count = data.get("new_count", 0)

            self._scan_result_label.configure(
                text=f"掃描完成：共 {total} 篇文章，{new_count} 篇新文章"
            )
            self._scan_result_label.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, 0))

            if urls:
                self._show_article_list(urls, titles)
            return

        if url == "__FETCH_DONE__":
            self._progress.set_complete()
            self._fetch_selected_btn.configure(state="normal")
            self._stats_label.configure(text=self._result_table.get_stats_text())
            self._stats_label.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, PAD_Y))
            return

        # 一般結果
        platform_name = "PTT"
        path = data.get("path", "")
        self._result_table.add_result(url, platform_name, status, path)
        self._stats_label.configure(text=self._result_table.get_stats_text())

    def _show_article_list(self, urls: list[str], titles: list[str]):
        """顯示文章列表（可勾選）"""
        self._checkboxes.clear()

        # 清除舊的 checkbox
        for w in self._articles_frame.winfo_children():
            w.destroy()

        for url, title in zip(urls, titles):
            var = ctk.BooleanVar(value=True)
            display = f"{title}  ({url.split('/')[-1]})"
            cb = ctk.CTkCheckBox(
                self._articles_frame, text=display,
                variable=var, font=FONT_SMALL,
                checkbox_width=18, checkbox_height=18,
            )
            cb.pack(fill="x", pady=1)
            self._checkboxes.append((var, url, title))

        self._articles_frame.pack(fill="both", expand=True,
                                  padx=PAD_X, pady=(PAD_INNER, 0))
        self._select_frame.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, 0))

    def _select_all(self):
        for var, _, _ in self._checkboxes:
            var.set(True)

    def _deselect_all(self):
        for var, _, _ in self._checkboxes:
            var.set(False)

    def _start_fetch_selected(self):
        """開始擷取選取的文章"""
        selected = [url for var, url, _ in self._checkboxes if var.get()]
        if not selected:
            from tkinter import messagebox
            messagebox.showwarning("無選取", "請至少選取一篇文章")
            return

        output_dir = self._output_entry.get().strip() or self.app.get_output_dir()

        self.task_id = f"ptt_fetch_{uuid.uuid4().hex[:8]}"
        self._fetch_selected_btn.configure(state="disabled")
        self._progress.show()
        self._result_table.clear()
        self._result_table.pack(fill="both", expand=True,
                                padx=PAD_X, pady=(PAD_INNER, 0))
        self._stats_label.configure(text="")
        self._stats_label.pack(fill="x", padx=PAD_X, pady=(PAD_INNER, PAD_Y))

        self.app.task_runner.submit(
            self.task_id,
            self._fetch_worker,
            selected, output_dir,
            progress_queue=self._progress_queue,
            result_queue=self._result_queue,
        )

    @staticmethod
    def _fetch_worker(urls, output_dir, cancel_event, progress_queue, result_queue):
        """背景逐一擷取文章"""
        total = len(urls)
        for i, url in enumerate(urls, 1):
            if cancel_event.is_set():
                break

            progress_queue.put((i, total, f"擷取中 ({i}/{total})：{url}"))

            try:
                article = scraper.fetch_article(url)
                if article:
                    save_path = scraper.save_article(article, output_dir)
                    scraper.mark_as_fetched(url, output_dir)
                    result_queue.put((url, "success", {"path": save_path or ""}))
                else:
                    result_queue.put((url, "failed", {}))
            except Exception as e:
                scraper.logger.error(f"擷取失敗 {url}: {e}")
                result_queue.put((url, "failed", {"error": str(e)}))

            if i < total and not cancel_event.is_set():
                time.sleep(scraper.POLITENESS_DELAY)

        progress_queue.put((total, total, "完成"))
        result_queue.put(("__FETCH_DONE__", "done", {}))

    def _cancel_task(self):
        """取消任務"""
        if self.task_id:
            self.app.task_runner.cancel(self.task_id)

    def _clear_scan_results(self):
        """清除掃描結果"""
        self._scan_result_label.pack_forget()
        self._articles_frame.pack_forget()
        self._select_frame.pack_forget()
        self._result_table.pack_forget()
        self._stats_label.pack_forget()
        self._checkboxes.clear()
        for w in self._articles_frame.winfo_children():
            w.destroy()
