# logging_setup.py
from __future__ import annotations
from pathlib import Path
import logging
from logging.handlers import TimedRotatingFileHandler
import sys

# 单例开关，避免重复添加 handler
_INITIALIZED = False
_CUR_DIR: Path | None = None

def setup_logging(logs_dir: str | Path | None = None) -> Path:
    """
    初始化分层日志。支持显式指定日志目录。
    - logs_dir=None：默认使用 项目根下的 logs（推断为 main.py 所在目录的上一级 /logs）
    - 返回最终的日志目录 Path
    """
    global _INITIALIZED, _CUR_DIR
    if _INITIALIZED and _CUR_DIR and logs_dir is None:
        return _CUR_DIR

    # 解析日志目录
    if logs_dir is not None:
        logs_path = Path(logs_dir).expanduser().resolve()
    else:
        # 默认：以启动脚本所在目录的父级为 root，使用 <root>/logs
        try:
            root = Path(sys.argv[0]).resolve().parent
            # 假设结构是 <project_root>/main.py -> root 就是 project_root
            logs_path = (root / "logs").resolve()
        except Exception:
            logs_path = Path("./logs").resolve()

    logs_path.mkdir(parents=True, exist_ok=True)

    # 清理旧 handler（防止重复初始化）
    for name in ("user", "system", "config"):
        logger = logging.getLogger(name)
        logger.handlers = []

    # 控制台（只挂在 system 上，便于开发时看）
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))

    def _mk_logger(name: str, filename: str, level: int):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        fh = TimedRotatingFileHandler(logs_path / filename, when="midnight", backupCount=14, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        logger.addHandler(fh)
        if name == "system":
            logger.addHandler(console)
        return logger

    _mk_logger("user",   "user.log",   logging.INFO)
    _mk_logger("system", "system.log", logging.INFO)
    _mk_logger("config", "config.log", logging.DEBUG)

    _INITIALIZED = True
    _CUR_DIR = logs_path
    return logs_path
