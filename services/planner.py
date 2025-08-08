# services/planner.py
from __future__ import annotations
from typing import Dict, Set

def quick_plan_from_validation(v_report: dict) -> dict:
    """
    从验证器报告中提炼 planned_skips，形成执行计划。
    v_report 结构见 validator.report
    """
    skip_sheets: Set[str] = set(v_report.get("planned_skips", {}).get("sheets", []))
    skip_paras:  Set[str] = set(v_report.get("planned_skips", {}).get("paragraphs", []))
    all_sheets  = set(v_report.get("excel", {}).get("sheets", []))
    all_paras   = set(v_report.get("paragraphs", {}).get("all", []))

    return {
        "sheets_skip": skip_sheets,
        "paras_skip":  skip_paras,
        "sheets_exec": sorted(list(all_sheets - skip_sheets)),
        "paras_exec":  sorted(list(all_paras  - skip_paras)),
    }
