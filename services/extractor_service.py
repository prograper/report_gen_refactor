# services/extractor_service.py
from __future__ import annotations
from pathlib import Path
import logging, traceback
import pandas as pd

from agents.registry import get_extractor
from utils.coerce import coerce_types

SYS_LOG  = logging.getLogger("system")
USER_LOG = logging.getLogger("user")
CFG_LOG  = logging.getLogger("config")

def run_extraction(xls: pd.ExcelFile, sheet_cfg: dict, plan: dict, ec, config_dir: Path) -> dict:
    extracted: dict[str, dict] = {}

    for sheet in xls.sheet_names:
        if sheet not in sheet_cfg:
            SYS_LOG.info(f"跳过未配置 Sheet：{sheet}")
            continue
        if sheet in plan["sheets_skip"]:
            SYS_LOG.warning(f"跳过存在问题 Sheet：{sheet}")
            continue

        cfg = sheet_cfg[sheet]
        try:
            df = xls.parse(sheet)
            SYS_LOG.info(f"开始抽取 Sheet：{sheet}")

            extractor = get_extractor("GenericExtractor")(
                df          = df,
                keys        = cfg["keys"],
                prompt_path = config_dir / "prompts" / cfg["prompt"],
                config_dir  = config_dir,
                provider    = cfg.get("provider", "qwen"),
                sheet_name  = sheet,
            )
            raw_values = extractor.extract() or {}
            cleaned    = coerce_types(sheet, raw_values, cfg.get("keys", {}), percent_as_fraction=True)
            extracted[sheet] = cleaned

            # 摘要日志
            head = ", ".join(f"{k}={cleaned[k]}" for k in list(cleaned.keys())[:10])
            USER_LOG.info(f"[抽取完成] {sheet}：{head}{' ...' if len(cleaned)>10 else ''}")

        except Exception as e:
            ec.add("error", f"EXTRACT:{sheet}", f"抽取失败：{e}", traceback.format_exc())
            continue

    return extracted
