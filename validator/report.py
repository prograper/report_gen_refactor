# validator/report.py
from __future__ import annotations
from pathlib import Path
import json

def make_report(
    sheet_cfg: dict,
    para_cfg: dict,
    excel_sheets: list[str],
    findings: list[dict],
    simulate_render: bool = False,
    placeholders: dict | None = None,
    simulate: dict | None = None,
) -> dict:
    severity = "ok"
    if any(f["level"] == "error" for f in findings): severity = "error"
    elif any(f["level"] == "warning" for f in findings): severity = "warning"

    # 计划跳过
    skip_sheets = sorted(list({ f.get("tag", ("", ""))[1] for f in findings
                                if f["level"] in ("warning","error") and f.get("tag", ("",""))[0] in ("sheet",) }))
    skip_paras  = sorted(list({ f.get("tag", ("", ""))[1] for f in findings
                                if f["level"] in ("warning","error") and f.get("tag", ("",""))[0] in ("para",) }))

    return {
        "severity": severity,
        "excel": {"sheets": excel_sheets or []},
        "sheets": list((sheet_cfg or {}).keys()),
        "paragraphs": {"all": list((para_cfg or {}).keys())},
        "findings": findings,
        "planned_skips": {"sheets": skip_sheets, "paragraphs": skip_paras},
        "simulate_render": simulate_render,
        "simulate": simulate or {"enabled": False, "ok": None, "error": None},
        "placeholders": placeholders or {"variables": [], "paragraphs": [], "others": [], "raw": []},
    }

def write_report_files(report: dict, root: Path):
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "validator_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # -------- Markdown 友好输出 --------
    lines = []
    lines.append("# Validator Report")
    lines.append(f"- severity: **{report['severity']}**")
    lines.append(f"- excel sheets: {len(report.get('excel',{}).get('sheets', []))}")
    lines.append(f"- config sheets: {len(report.get('sheets', []))}, paragraphs: {len(report.get('paragraphs',{}).get('all',[]))}")
    lines.append(f"- planned_skips: {report.get('planned_skips')}")
    sim = report.get("simulate", {})
    lines.append(f"- simulate_render: enabled={sim.get('enabled')}, ok={sim.get('ok')}, error={sim.get('error')}")
    lines.append("")

    # 占位符汇总（干净）
    ph = report.get("placeholders", {})
    if ph:
        lines.append("## Template Placeholders (clean)")
        if ph.get("variables"):
            lines.append("- **Variables**")
            for v in ph["variables"]:
                lines.append(f"  - `{v}`")
        if ph.get("paragraphs"):
            lines.append("- **Paragraph IDs**")
            for p in ph["paragraphs"]:
                lines.append(f"  - `{p}`")
        if ph.get("others"):
            lines.append("- **Others**")
            for o in ph["others"]:
                lines.append(f"  - `{o}`")
        lines.append("")

    # 发现项
    lines.append("## Findings")
    if not report.get("findings"):
        lines.append("- (none)")
    else:
        for f in report["findings"]:
            lines.append(f"- **{f['level'].upper()}** | {f['where']}: {f['msg']}")

    (logs / "validator_report.md").write_text("\n".join(lines), encoding="utf-8")
