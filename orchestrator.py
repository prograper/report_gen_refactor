# orchestrator.py
from __future__ import annotations
from pathlib import Path
import logging, json, traceback
import pandas as pd

from core.error_collector import ErrorCollector
from core.logging_setup import setup_logging
from io_utils.loaders import load_yaml, load_excel_first, load_template_exists
from io_utils.writers import write_docx, write_json
from services.planner import quick_plan_from_validation
from services.extractor_service import run_extraction
from services.generator_service import run_generation_and_fill
from services.renderer_service import render_word
from validator.validate import validate_configs  # 用于 quick validate

SYS_LOG  = logging.getLogger("system")
USER_LOG = logging.getLogger("user")
CFG_LOG  = logging.getLogger("config")

def run_pipeline(config_dir: Path, report_name: str, root: Path, logs_dir: Path | None = None):
    setup_logging(logs_dir or (config_dir.parent / "logs"))
    ec = ErrorCollector()

    # 1) 加载配置 & Excel
    try:
        sheet_cfg   = load_yaml(config_dir / "business_configs" / "sheet_tasks.yaml")
        para_cfg    = load_yaml(config_dir / "business_configs" / "paragraph_tasks.yaml")
        xls         = load_excel_first(config_dir / "input")
        SYS_LOG.info(f"载入配置：sheet={len(sheet_cfg)}，paragraphs={len(para_cfg)}；Excel={xls.io}")
    except Exception as e:
        ec.add("error", "LOAD", f"加载配置/Excel失败：{e}", traceback.format_exc())
        ec.dump(root); raise

    # 2) 轻量验证（不阻断，仅返回 planned_skips）
    v_report = validate_configs(config_dir, xls, simulate_render=False)
    plan     = quick_plan_from_validation(v_report)
    USER_LOG.info(f"计划执行：sheets={len(plan['sheets_exec'])} / paragraphs={len(plan['paras_exec'])}（其余跳过）")

    # 3) 抽取（嵌套 dict）
    extracted = run_extraction(xls, sheet_cfg, plan, ec, config_dir)

    # 4) 生成/直填
    gen_ctx   = run_generation_and_fill(para_cfg, extracted, plan, ec, config_dir)

    # 5) 渲染
    try:
        render_word(config_dir, report_name, extracted, gen_ctx)
    except Exception as e:
        ec.add("error", "RENDER", f"渲染失败：{e}", traceback.format_exc())

    # 6) 摘要
    ec.dump(root)
    sums = ec.summary()["counts"]
    SYS_LOG.info(f"Run Summary: errors={sums['errors']}, warnings={sums['warnings']}")
    USER_LOG.info("运行完成，详情见 logs/user.log / system.log / config.log / run_summary.json")
