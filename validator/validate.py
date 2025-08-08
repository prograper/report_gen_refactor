# validator/validate.py
from __future__ import annotations
from pathlib import Path
import logging
import pandas as pd

from io_utils.loaders import load_yaml, load_excel_first
from validator.rules import (
    check_yaml_and_files,
    check_excel_alignment,
    check_paragraph_keys,
    check_template_placeholders,
)
from validator.simulate import simulate_template_render
from validator.report import make_report, write_report_files

SYS_LOG = logging.getLogger("system")

def validate_configs(config_dir: Path, xls: pd.ExcelFile | None, simulate_render: bool = False) -> dict:
    sheet_cfg = load_yaml(config_dir / "business_configs" / "sheet_tasks.yaml")
    para_cfg  = load_yaml(config_dir / "business_configs" / "paragraph_tasks.yaml")

    findings = []
    placeholders_info = {"variables": [], "paragraphs": [], "others": [], "raw": []}
    sim_info = {"enabled": bool(simulate_render), "ok": None, "error": None}

    # 基础检查：YAML结构、prompt/模板存在
    findings += check_yaml_and_files(config_dir, sheet_cfg, para_cfg)

    # Excel 对齐
    excel_sheets = []
    if xls:
        excel_sheets = list(xls.sheet_names)
        findings += check_excel_alignment(sheet_cfg, excel_sheets)
        findings += check_paragraph_keys(para_cfg, sheet_cfg)

    # 模板占位符交叉校验（只输出干净占位符）
    tmpl_findings, placeholders_info = check_template_placeholders(config_dir, sheet_cfg, para_cfg)
    findings += tmpl_findings

    # ✅ 模拟渲染（严格模式），仅在 simulate_render=True 时执行
    if simulate_render:
        sim_findings, sim_status = simulate_template_render(config_dir, sheet_cfg, para_cfg)
        findings += sim_findings
        sim_info.update({"ok": sim_status.get("ok"), "error": sim_status.get("error")})

    report = make_report(
        sheet_cfg, para_cfg, excel_sheets, findings,
        simulate_render=simulate_render,
        placeholders=placeholders_info,
        simulate=sim_info,
    )
    return report

def validate_configs_cli(config_dir: Path, excel_path: Path | None, simulate_render: bool, strict: bool, root: Path) -> int:
    try:
        xls = None
        if excel_path:
            from pandas import ExcelFile
            xls = ExcelFile(excel_path)
        else:
            xls = load_excel_first(config_dir / "input")
        report = validate_configs(config_dir, xls, simulate_render=simulate_render)
        write_report_files(report, root)
        ok = (report.get("severity", "ok") in ("ok", "warning"))  # 有 error 则失败
        SYS_LOG.info(
            f"验证完成：severity={report.get('severity')}, "
            f"simulate={{enabled:{report.get('simulate',{}).get('enabled')}, ok:{report.get('simulate',{}).get('ok')}}}, "
            f"planned_skips={report.get('planned_skips')}"
        )
        return 0 if (ok or not strict) else 1
    except Exception as e:
        SYS_LOG.exception(f"验证异常：{e}")
        return 2
