"""
task_runner.py 單元測試
========================
測試背景任務執行器的核心功能和異常處理。
"""

import queue
import threading
import time
import logging
import pytest

from gui.workers.task_runner import TaskRunner, TASK_ERROR_SENTINEL


# ============================================================
# 基本功能
# ============================================================

class TestTaskRunnerBasic:
    def test_normal_task_completion(self):
        """正常任務完成，結果寫入 result_queue"""
        runner = TaskRunner(max_workers=1)
        result_q = queue.Queue()
        progress_q = queue.Queue()

        def worker(cancel_event=None, progress_queue=None, result_queue=None):
            if result_queue:
                result_queue.put(("test_url", "success", {}))

        runner.submit("test", worker, result_queue=result_q, progress_queue=progress_q)

        # 等待結果
        result = result_q.get(timeout=5)
        assert result == ("test_url", "success", {})
        runner.shutdown()

    def test_cancel_event(self):
        """取消任務設定 cancel_event"""
        runner = TaskRunner(max_workers=1)
        started = threading.Event()

        def worker(cancel_event=None, progress_queue=None, result_queue=None):
            started.set()
            # 等待取消信號
            cancel_event.wait(timeout=5)

        runner.submit("cancel_test", worker)
        started.wait(timeout=5)

        assert runner.is_running("cancel_test")
        result = runner.cancel("cancel_test")
        assert result is True
        runner.shutdown()

    def test_is_running(self):
        """查詢任務執行狀態"""
        runner = TaskRunner(max_workers=1)
        barrier = threading.Event()

        def worker(cancel_event=None, progress_queue=None, result_queue=None):
            barrier.wait(timeout=5)

        runner.submit("running_test", worker)
        time.sleep(0.1)  # 等任務啟動
        assert runner.is_running("running_test")

        barrier.set()
        time.sleep(0.3)  # 等任務結束
        assert not runner.is_running("running_test")
        runner.shutdown()


# ============================================================
# 異常處理
# ============================================================

class TestTaskRunnerExceptionHandling:
    def test_exception_logged_to_queue(self):
        """任務拋異常時，result_queue 收到 TASK_ERROR_SENTINEL"""
        runner = TaskRunner(max_workers=1)
        result_q = queue.Queue()

        def failing_worker(cancel_event=None, progress_queue=None, result_queue=None):
            raise ValueError("Worker exploded!")

        runner.submit("fail_test", failing_worker, result_queue=result_q)

        # 等待錯誤訊息
        result = result_q.get(timeout=5)
        assert result[0] == TASK_ERROR_SENTINEL
        assert "Worker exploded!" in result[1]
        runner.shutdown()

    def test_exception_logged_to_logger(self, caplog):
        """任務拋異常時，logger 有記錄"""
        runner = TaskRunner(max_workers=1)
        done = threading.Event()

        def failing_worker(cancel_event=None, progress_queue=None, result_queue=None):
            raise RuntimeError("Something broke")

        with caplog.at_level(logging.ERROR, logger="climb.task_runner"):
            future = runner.submit("log_test", failing_worker)
            # 等待任務結束
            try:
                future.result(timeout=5)
            except RuntimeError:
                pass

        # 稍等 cleanup callback 執行
        time.sleep(0.3)

        assert any("Something broke" in record.message for record in caplog.records)
        runner.shutdown()

    def test_cleanup_after_exception(self):
        """異常後 active_futures 已清理"""
        runner = TaskRunner(max_workers=1)

        def failing_worker(cancel_event=None, progress_queue=None, result_queue=None):
            raise RuntimeError("Crash!")

        future = runner.submit("cleanup_test", failing_worker)

        # 等待任務結束
        try:
            future.result(timeout=5)
        except RuntimeError:
            pass

        time.sleep(0.3)  # 等 cleanup callback
        assert not runner.is_running("cleanup_test")
        with runner._lock:
            assert "cleanup_test" not in runner._active_futures
            assert "cleanup_test" not in runner._cancel_events
        runner.shutdown()

    def test_exception_without_result_queue(self):
        """沒有 result_queue 時異常仍被 logger 記錄，不會 crash"""
        runner = TaskRunner(max_workers=1)

        def failing_worker(cancel_event=None, progress_queue=None, result_queue=None):
            raise RuntimeError("No queue crash")

        future = runner.submit("no_queue_test", failing_worker)

        # 應該不會因為 result_queue=None 而出額外錯誤
        try:
            future.result(timeout=5)
        except RuntimeError:
            pass

        time.sleep(0.3)
        assert not runner.is_running("no_queue_test")
        runner.shutdown()

    def test_error_sentinel_constant(self):
        """確認 TASK_ERROR_SENTINEL 是可用的字串常數"""
        assert isinstance(TASK_ERROR_SENTINEL, str)
        assert len(TASK_ERROR_SENTINEL) > 0
