import sys
import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


def setup_logging(log_level: str = "INFO", retention_days: int = 90) -> None:
    """
    全系統 logging 設定。

    產生三個 log 檔（每日 rotate）：
      logs/app.log   — INFO 以上，一般操作紀錄
      logs/debug.log — DEBUG 以上，開發用詳細紀錄
      logs/error.log — ERROR 以上，錯誤留存

    retention_days: 每個 log 檔保留幾天（預設 90 天）
    """
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)   # root 全開，由各 handler 各自過濾
    root.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    def _rotating(filename: str, level: int) -> TimedRotatingFileHandler:
        h = TimedRotatingFileHandler(
            filename=log_dir / filename,
            when="midnight",
            interval=1,
            backupCount=retention_days,
            encoding="utf-8",
            utc=False,
        )
        h.setLevel(level)
        h.setFormatter(fmt)
        h.suffix = "%Y%m%d"
        return h

    # Console
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(fmt)
    root.addHandler(console)

    # app.log — INFO+
    root.addHandler(_rotating("app.log", logging.INFO))

    # debug.log — DEBUG+
    root.addHandler(_rotating("debug.log", logging.DEBUG))

    # error.log — ERROR+
    root.addHandler(_rotating("error.log", logging.ERROR))


def get_logger(name: str) -> logging.Logger:
    """各模組取 logger 的統一入口。"""
    return logging.getLogger(name)
