"""
Extension API Server
====================
本地 HTTP API 伺服器，接收 Chrome Extension 傳來的文章資料，
呼叫 scraper.save_article() 儲存為統一格式。

端點：
  POST /save   — 接收文章 JSON，儲存到輸出目錄
  GET  /status — 健康檢查
  GET  /recent — 最近儲存的文章列表
  OPTIONS /*   — CORS preflight 回應
"""

import json
import os
import queue
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Optional

import scraper


class _CORSRequestHandler(BaseHTTPRequestHandler):
    """處理 CORS 和路由的 HTTP Request Handler"""

    # 類別層級屬性，由 ArticleAPIServer 設定
    _output_dir: str = ""
    _save_lock: threading.Lock = threading.Lock()
    _log_queue: Optional[queue.Queue] = None
    _port: int = 3456

    def _set_cors_headers(self):
        """設定 CORS headers（Chrome Extension 跨域存取必需）"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status_code: int, data: dict):
        """回傳 JSON 回應"""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._set_cors_headers()
        self.end_headers()
        body = json.dumps(data, ensure_ascii=False)
        self.wfile.write(body.encode("utf-8"))

    def do_OPTIONS(self):
        """處理 CORS preflight 請求"""
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        """處理 GET 請求"""
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/recent":
            self._handle_recent()
        else:
            self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self):
        """處理 POST 請求"""
        if self.path == "/save":
            self._handle_save()
        else:
            self._send_json(404, {"status": "error", "message": "Not found"})

    def _handle_status(self):
        """GET /status — 健康檢查"""
        self._send_json(200, {
            "status": "running",
            "port": self._port,
            "output_dir": self._output_dir,
            "version": "1.0.0",
        })

    def _handle_recent(self):
        """GET /recent — 最近儲存的文章列表"""
        articles = _scan_recent_articles(self._output_dir, limit=20)
        self._send_json(200, {
            "status": "ok",
            "articles": articles,
        })

    def _handle_save(self):
        """POST /save — 接收並儲存文章"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_json(400, {
                    "status": "error",
                    "message": "Empty request body",
                })
                return

            raw = self.rfile.read(content_length)
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._send_json(400, {
                "status": "error",
                "message": f"Invalid JSON: {e}",
            })
            return

        # 驗證必要欄位
        title = data.get("title", "").strip()
        content = data.get("content", "").strip()
        url = data.get("url", "").strip()

        if not title or not content:
            self._send_json(400, {
                "status": "error",
                "message": "Missing required fields: title and content",
            })
            return

        # 組裝 article dict（與 scraper.save_article 期望的格式一致）
        article = {
            "title": title,
            "content": content,
            "url": url,
            "platform": data.get("platform", "其他"),
            "source": data.get("source", "chrome-ext"),
            "images": data.get("images", []),
        }

        # 儲存文章（加鎖保護執行緒安全）
        try:
            with self._save_lock:
                save_path = scraper.save_article(article, self._output_dir)
                if url:
                    scraper.mark_as_fetched(url, self._output_dir)

            path_str = str(save_path).replace("\\", "/") if save_path else ""

            # 通知 GUI
            if self._log_queue:
                self._log_queue.put_nowait({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "title": title,
                    "platform": article["platform"],
                    "url": url,
                    "status": "success",
                    "path": path_str,
                })

            scraper.logger.info(
                f"[Extension] 已儲存：{title} ({article['platform']})"
            )

            self._send_json(200, {
                "status": "ok",
                "path": path_str,
                "title": title,
            })

        except Exception as e:
            scraper.logger.error(f"[Extension] 儲存失敗：{e}")

            if self._log_queue:
                self._log_queue.put_nowait({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "title": title,
                    "platform": article["platform"],
                    "url": url,
                    "status": "failed",
                    "error": str(e),
                })

            self._send_json(500, {
                "status": "error",
                "message": str(e),
            })

    def log_message(self, format, *args):
        """覆寫預設 log 輸出，改用 scraper.logger"""
        scraper.logger.debug(f"[API Server] {args[0]}")


def _scan_recent_articles(output_dir: str, limit: int = 20) -> list[dict]:
    """掃描輸出目錄中最近的文章 metadata"""
    output_path = Path(os.path.expanduser(output_dir))
    if not output_path.exists():
        return []

    articles = []
    for metadata_path in output_path.rglob("metadata.json"):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["_dir"] = str(metadata_path.parent).replace("\\", "/")
            articles.append(meta)
        except Exception:
            continue

    # 依 fetched_at 排序（最新在前）
    articles.sort(key=lambda x: x.get("fetched_at", ""), reverse=True)
    return articles[:limit]


class ArticleAPIServer:
    """Extension API Server — 管理本地 HTTP 伺服器的生命週期"""

    def __init__(
        self,
        port: int = 3456,
        output_dir: str = "",
        log_queue: Optional[queue.Queue] = None,
    ):
        self.port = port
        self.output_dir = output_dir or scraper.DEFAULT_OUTPUT_DIR
        self.log_queue = log_queue

        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> tuple[bool, str]:
        """啟動 API Server

        Returns:
            (success: bool, message: str)
        """
        if self._running:
            return True, f"伺服器已在 port {self.port} 運行中"

        try:
            # 設定 Handler 的類別屬性
            _CORSRequestHandler._output_dir = os.path.expanduser(self.output_dir)
            _CORSRequestHandler._save_lock = threading.Lock()
            _CORSRequestHandler._log_queue = self.log_queue
            _CORSRequestHandler._port = self.port

            self._server = HTTPServer(("127.0.0.1", self.port), _CORSRequestHandler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True,
                name="CLIMB-API-Server",
            )
            self._thread.start()
            self._running = True

            scraper.logger.info(
                f"[Extension] API Server 已啟動 — http://localhost:{self.port}"
            )
            return True, f"伺服器已啟動 (port {self.port})"

        except OSError as e:
            msg = f"無法啟動伺服器 (port {self.port})：{e}"
            scraper.logger.error(f"[Extension] {msg}")
            return False, msg

    def stop(self):
        """停止 API Server"""
        if self._server:
            self._server.shutdown()
            self._server = None
        self._thread = None
        self._running = False
        scraper.logger.info("[Extension] API Server 已停止")

    def is_running(self) -> bool:
        """查詢伺服器是否運行中"""
        return self._running

    def update_output_dir(self, output_dir: str):
        """更新輸出目錄（不需重啟 server）"""
        self.output_dir = output_dir
        _CORSRequestHandler._output_dir = os.path.expanduser(output_dir)
