# utils/coerce.py
from __future__ import annotations
import logging
SYS_LOG = logging.getLogger("system")

def coerce_types(sheet: str, values: dict, type_spec: dict, percent_as_fraction: bool = True) -> dict:
    out: dict = {}
    for k, typ in (type_spec or {}).items():
        v = values.get(k, None)
        if v is None:
            out[k] = None;  continue
        try:
            if typ == "number":
                s = str(v).strip()
                is_percent = s.endswith("%")
                s = s.replace(",", "").replace("%", "").strip()
                num = float(s)
                if is_percent:
                    num = num / 100.0 if percent_as_fraction else num
                out[k] = num
            elif typ == "array[string]":
                out[k] = [str(x) for x in (v if isinstance(v, list) else [v])]
            else:
                out[k] = str(v)
        except Exception as e:
            out[k] = None
            SYS_LOG.warning(f"[COERCE-FAIL] {sheet}.{k} 类型 {typ} 转换失败（值={v}）：{e}")
    return out
