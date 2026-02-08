"""
背景任務執行器
===============
封裝 ThreadPoolExecutor，提供任務提交、取消、狀態查詢。
所有頁籤透過此模組在背景執行緒中呼叫 scraper 函式。

異常處理：
  worker 拋出未捕獲的異常時，會透過 result_queue 送出
  ("__TASK_ERROR__", error_message) 供 GUI 顯示錯誤訊息，
  同時記錄到 logger。
"""

import logging
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Any, Optional

logger = logging.getLogger("climb.task_runner")

# 錯誤 sentinel — 頁籤的 poll_queues 可檢查此值
TASK_ERROR_SENTINEL = "__TASK_ERROR__"


class TaskRunner:
    """執行緒池管理器 — 管理背景任務的生命週期"""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._active_futures: dict[str, Future] = {}
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _make_safe_worker(
        fn: Callable,
        task_id: str,
        result_queue: Optional[queue.Queue],
    ) -> Callable:
        """包裝 worker 函式，確保未捕獲的異常被記錄到 logger 和 result_queue。

        Args:
            fn: 原始 worker 函式
            task_id: 任務識別碼（用於 log）
            result_queue: 結果 queue（可為 None）

        Returns:
            包裝後的函式
        """
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"任務 {task_id} 發生未捕獲的異常：{e}",
                    exc_info=True,
                )
                if result_queue:
                    try:
                        result_queue.put((TASK_ERROR_SENTINEL, str(e)))
                    except Exception:
                        pass  # queue 本身出問題也不能讓 wrapper 崩潰
                raise  # 重新拋出，讓 Future 記錄異常
        return wrapper

    def submit(
        self,
        task_id: str,
        fn: Callable,
        *args,
        progress_queue: Optional[queue.Queue] = None,
        result_queue: Optional[queue.Queue] = None,
        **kwargs
    ) -> Future:
        """提交背景任務

        Args:
            task_id: 唯一任務識別碼
            fn: 要執行的函式
            *args: 傳給 fn 的位置參數
            progress_queue: 進度更新 queue (current, total, message)
            result_queue: 結果 queue (url, status, data)
            **kwargs: 傳給 fn 的關鍵字參數

        Returns:
            Future 物件
        """
        cancel_event = threading.Event()

        with self._lock:
            # 如果同 task_id 還在執行，先取消
            if task_id in self._cancel_events:
                self._cancel_events[task_id].set()
            self._cancel_events[task_id] = cancel_event

        # 用安全包裝器包住 worker，確保異常被記錄
        safe_fn = self._make_safe_worker(fn, task_id, result_queue)

        future = self._executor.submit(
            safe_fn, *args,
            cancel_event=cancel_event,
            progress_queue=progress_queue,
            result_queue=result_queue,
            **kwargs
        )

        with self._lock:
            self._active_futures[task_id] = future

        # 任務結束時清理 + 記錄異常
        def _cleanup(f):
            with self._lock:
                self._active_futures.pop(task_id, None)
                self._cancel_events.pop(task_id, None)
            # 記錄 Future 層級的異常（補充保險）
            exc = f.exception()
            if exc:
                logger.error(f"任務 {task_id} 異常結束：{exc}")

        future.add_done_callback(_cleanup)
        return future

    def cancel(self, task_id: str) -> bool:
        """取消指定任務（設定 cancel_event，等待任務自行停止）"""
        with self._lock:
            event = self._cancel_events.get(task_id)
            if event:
                event.set()
                return True
            return False

    def is_running(self, task_id: str) -> bool:
        """查詢指定任務是否正在執行"""
        with self._lock:
            future = self._active_futures.get(task_id)
            return future is not None and not future.done()

    def shutdown(self):
        """關閉執行緒池（取消所有任務）"""
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
        self._executor.shutdown(wait=False)
