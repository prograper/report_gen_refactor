# validator/simulate.py
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Tuple, List
from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined

# 生成虚拟上下文：模仿运行时的 render_ctx = {**extracted, **gen_ctx}
def build_fake_context(sheet_cfg: dict, para_cfg: dict) -> dict:
    def fake_by_type(t: str):
        if t == "number":
            return 123.45
        if t == "array[string]":
            return ["alpha", "beta"]
        return "示例"

    ctx: Dict[str, Any] = {}

    # 每个 sheet -> {field: fake_value}
    for sheet, cfg in (sheet_cfg or {}).items():
        fields = cfg.get("keys", {}) or {}
        ctx[sheet] = {k: fake_by_type(t) for k, t in fields.items()}

    # generate 段落 -> 文本占位
    for pid, task in (para_cfg or {}).items():
        mode = task.get("mode") or ("generate" if "prompt" in task else "fill")
        if mode == "generate":
            ctx[pid] = f"[GENERATED:{pid}]"

    return ctx

def simulate_template_render(config_dir: Path, sheet_cfg: dict, para_cfg: dict) -> Tuple[List[dict], dict]:
    """
    使用严格 Jinja 环境（StrictUndefined）在内存中渲染一次模板。
    - 成功：返回 ([], {"ok": True})
    - 失败：返回 ([{level:'error', where:'RENDER', msg:...}], {"ok": False, "error": str})
    """
    tpl_path = config_dir / "template" / "report_template.docx"
    if not tpl_path.exists():
        return ([{"level": "error", "where": "RENDER", "msg": f"模板不存在：{tpl_path}"}], {"ok": False, "error": "template_not_found"})

    fake_ctx = build_fake_context(sheet_cfg, para_cfg)

    try:
        doc = DocxTemplate(tpl_path)
        # 使用 StrictUndefined：任何未定义变量/占位符都会抛错
        env = Environment(undefined=StrictUndefined, autoescape=False)
        # ⚠️ 不保存文件，只做内存渲染
        doc.render(fake_ctx, jinja_env=env)
        return ([], {"ok": True})
    except Exception as e:
        return ([{"level": "error", "where": "RENDER", "msg": f"模板模拟渲染失败：{e}"}], {"ok": False, "error": str(e)})
