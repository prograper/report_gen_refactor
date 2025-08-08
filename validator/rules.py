# validator/rules.py
from __future__ import annotations
from pathlib import Path
import re

from validator.docx_scan import scan_placeholders

SUPPORTED_TYPES = {"string", "number", "array[string]"}

VAR_PATH_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")     # 例：sum_total.total_recov_rate
SIMPLE_ID_RE = re.compile(r"^[A-Za-z_]\w*$")                      # 例：Conclusion / Excretion

def _exists(p: Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False

def _warn(where, msg, tag=None): return {"level": "warning", "where": where, "msg": msg, "tag": tag}
def _err(where, msg, tag=None):  return {"level": "error",   "where": where, "msg": msg, "tag": tag}

# ---------------- 基础校验（原有） ----------------
def check_yaml_and_files(config_dir: Path, sheet_cfg: dict, para_cfg: dict) -> list[dict]:
    findings = []

    # sheet_tasks 基础
    for sname, cfg in (sheet_cfg or {}).items():
        if not isinstance(cfg, dict):
            findings.append(_warn("CONFIG", f"sheet {sname} 配置不是对象，将跳过", tag=("sheet", sname)))
            continue
        p_rel = cfg.get("prompt")
        if not p_rel:
            findings.append(_warn("CONFIG", f"sheet {sname} 缺少 prompt，将跳过", tag=("sheet", sname)));  continue
        p_abs = config_dir / "prompts" / p_rel
        if not _exists(p_abs):
            findings.append(_warn("CONFIG", f"sheet {sname} 的 prompt 文件不存在：{p_abs}", tag=("sheet", sname)))
        keys = cfg.get("keys", {})
        if not isinstance(keys, dict) or not keys:
            findings.append(_warn("CONFIG", f"sheet {sname} 的 keys 非法或为空，将跳过", tag=("sheet", sname)))
        for k, t in keys.items():
            if "." in k:
                findings.append(_err("CONFIG", f"字段名不允许含 '.'：{sname}.{k}", tag=("field", f"{sname}.{k}")))
            if t not in SUPPORTED_TYPES:
                findings.append(_warn("CONFIG", f"不支持的类型 {t}：按 string 处理（{sname}.{k}）", tag=("field", f"{sname}.{k}")))

    # paragraphs 基础
    for pid, task in (para_cfg or {}).items():
        if not isinstance(task, dict):
            findings.append(_warn("CONFIG", f"段落 {pid} 配置不是对象，将跳过", tag=("para", pid)));  continue
        mode = task.get("mode") or ("generate" if "prompt" in task else "fill")
        if mode not in ("generate", "fill"):
            findings.append(_warn("CONFIG", f"段落 {pid} 的 mode 非 generate/fill，将跳过", tag=("para", pid)));  continue
        if mode == "generate":
            p_rel = task.get("prompt")
            if not p_rel:
                findings.append(_err("CONFIG", f"段落 {pid} 缺少 prompt", tag=("para", pid)));  continue
            p_abs = config_dir / "prompts" / p_rel
            if not _exists(p_abs):
                findings.append(_err("CONFIG", f"段落 {pid} 的 prompt 文件不存在：{p_abs}", tag=("para", pid)))
        keys = task.get("keys", [])
        if keys and not isinstance(keys, list):
            findings.append(_warn("CONFIG", f"段落 {pid} 的 keys 不是列表，将忽略", tag=("para", pid)))

    # 模板存在性
    tpl = config_dir / "template" / "report_template.docx"
    if not _exists(tpl):
        findings.append(_err("CONFIG", f"模板不存在：{tpl}", tag=("template", "report_template.docx")))

    return findings

def check_excel_alignment(sheet_cfg: dict, excel_sheets: list[str]) -> list[dict]:
    findings = []
    excel_set = set(excel_sheets)
    for sname in (sheet_cfg or {}).keys():
        if sname not in excel_set:
            findings.append(_warn("EXCEL", f"Excel 中不存在 Sheet：{sname}（将跳过）", tag=("sheet", sname)))
    return findings

def check_paragraph_keys(para_cfg: dict, sheet_cfg: dict) -> list[dict]:
    findings = []
    for pid, task in (para_cfg or {}).items():
        keys = task.get("keys", []) or []
        for k in keys:
            if "." not in k:
                findings.append(_warn("KEY", f"{pid} 的 key 缺少 '.'：{k}", tag=("para", pid)))
                continue
            sheet, field = k.split(".", 1)
            if sheet not in (sheet_cfg or {}):
                findings.append(_err("KEY", f"{pid} 引用了未知 Sheet：{k}", tag=("para", pid)))
            elif field not in (sheet_cfg[sheet].get("keys", {}) or {}):
                findings.append(_warn("KEY", f"{pid} 的字段不在 {sheet}.keys 声明中：{k}", tag=("para", pid)))
    return findings

# ---------------- 模板占位符交叉校验（新版） ----------------
def check_template_placeholders(config_dir: Path, sheet_cfg: dict, para_cfg: dict):
    """
    返回 findings（列表）和 placeholder_info（字典），全部是“干净占位符”。
    """
    placeholders = scan_placeholders(config_dir / "template" / "report_template.docx")

    variables_paths: set[str] = set()  # 纯变量路径（可能来自一个占位符内的多个路径）
    para_ids: set[str] = set()
    others: set[str] = set()
    findings = []

    for expr in placeholders:
        expr_str = expr.strip()

        # 先抓出所有变量路径（允许 filters/运算）
        var_paths = VAR_PATH_RE.findall(expr_str)

        if var_paths:
            # 校验每个变量路径：Sheet.Field 是否在 sheet_cfg 中声明
            for path in var_paths:
                variables_paths.add(path)
                sheet, field, *_ = path.split(".")
                if sheet not in (sheet_cfg or {}):
                    findings.append(_err("TEMPLATE", f"模板变量引用未知 Sheet：`{path}`", tag=("tpl-var", path)))
                elif field not in (sheet_cfg[sheet].get("keys", {}) or {}):
                    findings.append(_warn("TEMPLATE", f"模板变量字段未在 keys 声明：`{path}`", tag=("tpl-var", path)))
            continue

        # 否则，若是简单标识符，当“段落占位符”
        if SIMPLE_ID_RE.match(expr_str):
            para_ids.add(expr_str)
            if expr_str not in (para_cfg or {}):
                findings.append(_warn("TEMPLATE", f"模板段落占位符未在 paragraph_tasks 声明：`{expr_str}`", tag=("tpl-para", expr_str)))
            else:
                mode = para_cfg[expr_str].get("mode") or ("generate" if "prompt" in para_cfg[expr_str] else "fill")
                if mode != "generate":
                    findings.append(_warn("TEMPLATE", f"模板期望段落文本，但 `{expr_str}` 配置为 fill", tag=("tpl-para", expr_str)))
            continue

        # 其它复杂表达式（例如调用、循环等），不作为错误，仅记录
        others.add(expr_str)

    # 多余的 generate 配置但模板未用
    for pid, task in (para_cfg or {}).items():
        mode = task.get("mode") or ("generate" if "prompt" in task else "fill")
        if mode == "generate" and pid not in para_ids:
            findings.append(_warn("TEMPLATE", f"段落 `{pid}` 配置为 generate，但模板未使用该占位符", tag=("para", pid)))

    placeholder_info = {
        "variables": sorted(variables_paths),
        "paragraphs": sorted(para_ids),
        "others": sorted(others),
        "raw": placeholders,  # 仅为完整性保留（已是干净表达式）
    }
    return findings, placeholder_info
