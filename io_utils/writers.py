# io/writers.py
from __future__ import annotations
from pathlib import Path
from docxtpl import DocxTemplate

def write_docx(config_dir: Path, report_name: str, render_ctx: dict):
    tpl = DocxTemplate(config_dir / "template" / "report_template.docx")
    tpl.render(render_ctx)
    out_dir = config_dir / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{report_name}.docx"
    tpl.save(out_path)
    return out_path

def write_json(path: Path, data: dict):
    import json
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
