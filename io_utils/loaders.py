# io/loaders.py
from __future__ import annotations
from pathlib import Path
import yaml, pandas as pd

def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_excel_first(input_dir: Path, pattern: str="*.xls*") -> pd.ExcelFile:
    matches = sorted(Path(input_dir).glob(pattern))
    if not matches:
        raise FileNotFoundError(f"目录 {input_dir} 下没有找到任何 {pattern} 文件！")
    if len(matches) > 1:
        import logging; logging.getLogger("system").warning(f"发现 {len(matches)} 个 Excel，仅使用第一个：{matches[0].name}")
    return pd.ExcelFile(matches[0])

def load_template_exists(config_dir: Path) -> Path:
    p = config_dir / "template" / "report_template.docx"
    if not p.exists():
        raise FileNotFoundError(f"模板不存在：{p}")
    return p
