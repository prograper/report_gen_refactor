# validator/validate.py
from __future__ import annotations
from pathlib import Path
import logging
import pandas as pd

from io_utils.loaders import load_yaml_strict, load_excel_first
from validator.rules import (
    check_yaml_and_files,
    check_excel_alignment,
    check_paragraph_keys,
    check_template_placeholders,
    check_naming_conflicts,
)
from validator.simulate import simulate_template_render
from validator.report import make_report, write_report_files
from core.logging_setup import setup_logging

SYS_LOG = logging.getLogger("system")

def validate_configs(config_dir: Path, xls: pd.ExcelFile | None, simulate_render: bool = False) -> dict:
    findings = []
    placeholders_info = {"variables": [], "paragraphs": [], "others": [], "raw": []}
    sim_info = {"enabled": bool(simulate_render), "ok": None, "error": None}

    # ---- 严格加载 YAML（可拿到解析错误 & 重复键） ----
    sheet_cfg, sheet_dups, sheet_err = load_yaml_strict(config_dir / "business_configs" / "sheet_tasks.yaml")
    para_cfg,  para_dups,  para_err  = load_yaml_strict(config_dir / "business_configs" / "paragraph_tasks.yaml")

    if sheet_err:
        findings.append({"level":"error","where":"CONFIG","msg":f"[FATAL] {sheet_err}"})
        sheet_cfg = sheet_cfg or {}
    if para_err:
        findings.append({"level":"error","where":"CONFIG","msg":f"[FATAL] {para_err}"})
        para_cfg = para_cfg or {}

    for d in sheet_dups or []:
        findings.append({"level":"warning","where":"CONFIG","msg":f"sheet_tasks 存在重复键 `{d['key']}` @ {d['where']}"})
    for d in para_dups or []:
        findings.append({"level":"warning","where":"CONFIG","msg":f"paragraph_tasks 存在重复键 `{d['key']}` @ {d['where']}"})

    # ---- 基础结构与文件存在性 ----
    findings += check_yaml_and_files(config_dir, sheet_cfg, para_cfg)

    # ---- Excel 对齐 & keys 引用合法性 ----
    excel_sheets = []
    if xls:
        excel_sheets = list(xls.sheet_names)
        findings += check_excel_alignment(sheet_cfg, excel_sheets)
        findings += check_paragraph_keys(para_cfg, sheet_cfg)

    # ---- 命名冲突（段落ID vs Sheet 名） ----
    findings += check_naming_conflicts(sheet_cfg, para_cfg)

    # ---- 模板占位符交叉校验（干净表达式）----
    tmpl_findings, placeholders_info = check_template_placeholders(config_dir, sheet_cfg, para_cfg)
    findings += tmpl_findings

    # ---- 可选：模板模拟渲染（StrictUndefined）----
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

def validate_configs_cli(
    config_dir: Path,
    excel_path: Path | None,
    simulate_render: bool,
    strict: bool,
    root: Path,
    logs_dir: Path | None = None,
) -> int:
    """
    CLI 入口：增加 logs_dir 可选参数。
    - 若提供 logs_dir：日志初始化与报告写入都使用 logs_dir
    - 否则：默认使用 <root>/logs
    """
    try:
        # 初始化日志（验证阶段也输出到指定日志目录）
        setup_logging(logs_dir if logs_dir is not None else (root / "logs"))

        xls = None
        if excel_path:
            from pandas import ExcelFile
            xls = ExcelFile(excel_path)
        else:
            try:
                xls = load_excel_first(config_dir / "input")
            except Exception as _:
                xls = None

        report = validate_configs(config_dir, xls, simulate_render=simulate_render)

        # 写报告
        write_report_files(
            report,
            root=root,
            logs_dir=logs_dir  # 若为 None，会落到 <root>/logs
        )

        ok = (report.get("severity", "ok") in ("ok", "warning"))
        SYS_LOG.info(
            f"验证完成：severity={report.get('severity')}, "
            f"simulate={{enabled:{report.get('simulate',{}).get('enabled')}, ok:{report.get('simulate',{}).get('ok')}}}, "
            f"planned_skips={report.get('planned_skips')}"
        )
        return 0 if (ok or not strict) else 1
    except Exception as e:
        SYS_LOG.exception(f"验证异常：{e}")
        return 2
