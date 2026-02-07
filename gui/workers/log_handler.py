"""
GUI 日誌處理器
===============
將 logging 日誌導向 queue.Queue，供 GUI 主執行緒消費顯示。
"""

import logging
import queue


class GUILogHandler(logging.Handler):
    """自訂 logging.Handler，將格式化日誌訊息放入 Queue"""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        ))

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.log_queue.put_nowait((record.levelname, msg))
        except Exception:
            self.handleError(record)
