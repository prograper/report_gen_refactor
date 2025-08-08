# core/error_collector.py
from __future__ import annotations
from pathlib import Path
import json, logging
USER_LOG = logging.getLogger("user"); SYS_LOG = logging.getLogger("system")

class ErrorCollector:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, level: str, where: str, msg: str, detail: str | None = None):
        rec = {"level": level, "where": where, "msg": msg}
        if detail: rec["detail"] = detail
        self.items.append(rec)
        if level.lower().startswith("warn"):
            USER_LOG.warning(f"[{where}] {msg}")
        else:
            SYS_LOG.error(f"[{where}] {msg}")

    def summary(self) -> dict:
        counts = {"errors": 0, "warnings": 0}
        for it in self.items:
            if it["level"].lower().startswith("warn"):
                counts["warnings"] += 1
            else:
                counts["errors"] += 1
        return {"counts": counts, "items": self.items}

    def dump(self, root: Path):
        (root / "logs").mkdir(exist_ok=True)
        (root / "logs" / "run_summary.json").write_text(
            json.dumps(self.summary(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
