# services/renderer_service.py
from __future__ import annotations
from pathlib import Path
import logging
from io_utils.writers import write_docx

SYS_LOG = logging.getLogger("system")

def render_word(config_dir: Path, report_name: str, extracted: dict, gen_ctx: dict):
    # 生成段落优先覆盖同名键
    render_ctx = {**extracted, **gen_ctx}
    write_docx(config_dir, report_name, render_ctx)
    SYS_LOG.info("流水线结束")
