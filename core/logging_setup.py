# logging_setup.py
from __future__ import annotations
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

def setup_logging(root: Path):
    """
    初始化三种日志：
      - user   : 用户可读的业务进度（INFO）
      - system : 系统运行状态（INFO+到控制台）
      - config : 配置/提示词/Schema 等调试信息（DEBUG）
    日志保存到 <root>/logs/*.log
    """
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    def make_logger(name: str, filename: str, level: int, to_console: bool=False):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(level)

        fh = TimedRotatingFileHandler(
            logs_dir / filename,
            when="midnight",
            backupCount=14,
            encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        if to_console:
            ch = logging.StreamHandler()
            ch.setFormatter(fmt)
            ch.setLevel(level)
            logger.addHandler(ch)

        logger.propagate = False
        return logger

    # 三类日志
    make_logger("user",   "user.log",   logging.INFO)
    make_logger("system", "system.log", logging.INFO, to_console=True)
    make_logger("config", "config.log", logging.DEBUG)

    return {
        "user":   logging.getLogger("user"),
        "system": logging.getLogger("system"),
        "config": logging.getLogger("config"),
    }
