# validator/rules.py
from __future__ import annotations
from pathlib import Path
import re
from typing import List, Dict, Tuple

from validator.docx_scan import scan_placeholders

SUPPORTED_TYPES = {"string", "number", "array[string]"}
# 字段名/段落ID约束：禁止 '.' / 花括号 / 空白；不强制英文，尽量宽松
ILLEGAL_CHARS_RE = re.compile(r"[.\s{}]")
SIMPLE_ID_RE = re.compile(r"^[^\s.{}][^\s{}]*$")  # 段落ID：不含空格/点/花括号
VAR_PATH_RE = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")

def _exists(p: Path) -> bool:
    try:
        return p.exists()
    except Exception:
        return False

def _warn(where, msg, tag=None): return {"level": "warning", "where": where, "msg": msg, "tag": tag}
def _err(where, msg, tag=None):  return {"level": "error",   "where": where, "msg": msg, "tag": tag}
def _fatal(where, msg, tag=None):return {"level": "error",   "where": where, "msg": f"[FATAL] {msg}", "tag": tag}

def _is_safe_relative(path_str: str) -> bool:
    # 仅允许相对路径，且不含 .. 片段
    p = Path(path_str)
    if p.is_absolute():
        return False
    if any(part == ".." for part in p.parts):
        return False
    return True

def check_yaml_and_files(config_dir: Path, sheet_cfg: dict, para_cfg: dict) -> list[dict]:
    """对 YAML 结构 & 文件存在性做稳健校验（容错 None/类型错误）。"""
    findings: List[Dict] = []

    # ---------- sheet_tasks 基础 ----------
    if not isinstance(sheet_cfg, dict):
        findings.append(_fatal("CONFIG", f"sheet_tasks 不是对象，而是 {type(sheet_cfg).__name__}；将按空配置处理"))
        sheet_cfg = {}

    for sname, cfg in (sheet_cfg or {}).items():
        if not isinstance(cfg, dict):
            findings.append(_warn("CONFIG", f"sheet {sname} 配置不是对象，将跳过", tag=("sheet", sname)))
            # 不 return，继续其它 sheet
            continue

        # prompt
        p_rel = cfg.get("prompt")
        if not p_rel:
            findings.append(_warn("CONFIG", f"sheet {sname} 缺少 prompt，将跳过抽取", tag=("sheet", sname)))
        else:
            if not _is_safe_relative(p_rel):
                findings.append(_err("CONFIG", f"sheet {sname} 的 prompt 路径不安全（只允许相对路径且不得包含 ..）：{p_rel}", tag=("sheet", sname)))
            p_abs = config_dir / "prompts" / p_rel
            if not _exists(p_abs):
                findings.append(_warn("CONFIG", f"sheet {sname} 的 prompt 文件不存在：{p_abs}", tag=("sheet", sname)))
            elif p_abs.is_dir():
                findings.append(_err("CONFIG", f"sheet {sname} 的 prompt 指向目录而非文件：{p_abs}", tag=("sheet", sname)))

        # keys
        keys = cfg.get("keys", {})
        if not isinstance(keys, dict) or not keys:
            findings.append(_warn("CONFIG", f"sheet {sname} 的 keys 缺失/为空/类型非法，将跳过该 Sheet", tag=("sheet", sname)))
            keys = {}

        for field_name, typ in keys.items():
            # 字段名校验
            if not isinstance(field_name, str) or not field_name.strip():
                findings.append(_err("CONFIG", f"{sname} 中存在非法字段名（空或非字符串）", tag=("field", f"{sname}.<invalid>")))
                continue
            if "." in field_name:
                findings.append(_err("CONFIG", f"字段名不允许含 '.'：{sname}.{field_name}", tag=("field", f"{sname}.{field_name}")))
            elif ILLEGAL_CHARS_RE.search(field_name):
                findings.append(_warn("CONFIG", f"字段名包含空白/花括号等不推荐字符：{sname}.{field_name}", tag=("field", f"{sname}.{field_name}")))
            # 类型校验
            if typ not in SUPPORTED_TYPES:
                findings.append(_warn("CONFIG", f"不支持的类型 {typ}：按 string 处理（{sname}.{field_name}）", tag=("field", f"{sname}.{field_name}")))

        # provider（可选）软校验
        provider = cfg.get("provider")
        if provider:
            prov = str(provider).lower().strip()
            if prov not in {"qwen", "openai"}:
                findings.append(_warn("CONFIG", f"未知 provider={provider}：将回退默认", tag=("sheet", sname)))
            else:
                # 环境变量提示（不读取值）
                need_env = "DASHSCOPE_API_KEY" if prov == "qwen" else "OPENAI_API_KEY"
                import os
                if not os.environ.get(need_env):
                    findings.append(_warn("CONFIG", f"provider={prov} 未检测到 {need_env} 环境变量（可能导致运行时报 401）", tag=("sheet", sname)))

    # ---------- paragraphs 基础 ----------
    if not isinstance(para_cfg, dict):
        findings.append(_fatal("CONFIG", f"paragraph_tasks 不是对象，而是 {type(para_cfg).__name__}；将按空配置处理"))
        para_cfg = {}

    for pid, task in (para_cfg or {}).items():
        if not isinstance(task, dict):
            findings.append(_warn("CONFIG", f"段落 {pid} 配置不是对象，将跳过", tag=("para", pid)))
            continue

        # 段落ID命名
        if not isinstance(pid, str) or not pid.strip():
            findings.append(_err("CONFIG", f"存在非法段落ID（空或非字符串）", tag=("para", "<invalid>")))
            continue
        if not SIMPLE_ID_RE.match(pid):
            findings.append(_warn("CONFIG", f"段落ID包含空格/点/花括号，可能影响模板解析：{pid}", tag=("para", pid)))

        mode = (task.get("mode") or ("generate" if "prompt" in task else "fill")).strip().lower()
        if mode not in ("generate", "fill"):
            findings.append(_warn("CONFIG", f"段落 {pid} 的 mode 非 generate/fill：{task.get('mode')}；将按隐式规则解释", tag=("para", pid)))
            mode = "generate" if "prompt" in task else "fill"

        # prompt 校验
        if mode == "generate":
            p_rel = task.get("prompt")
            if not p_rel:
                findings.append(_err("CONFIG", f"段落 {pid} 缺少 prompt", tag=("para", pid)))
            else:
                if not _is_safe_relative(p_rel):
                    findings.append(_err("CONFIG", f"段落 {pid} 的 prompt 路径不安全（仅允许相对路径且不得包含 ..）：{p_rel}", tag=("para", pid)))
                p_abs = config_dir / "prompts" / p_rel
                if not _exists(p_abs):
                    findings.append(_err("CONFIG", f"段落 {pid} 的 prompt 文件不存在：{p_abs}", tag=("para", pid)))
                elif p_abs.is_dir():
                    findings.append(_err("CONFIG", f"段落 {pid} 的 prompt 指向目录而非文件：{p_abs}", tag=("para", pid)))
        else:  # fill
            if "prompt" in task:
                findings.append(_warn("CONFIG", f"段落 {pid} 配置为 fill，但提供了 prompt（将被忽略）", tag=("para", pid)))

        # keys 校验
        keys = task.get("keys", [])
        if keys and not isinstance(keys, list):
            findings.append(_warn("CONFIG", f"段落 {pid} 的 keys 不是列表，将忽略", tag=("para", pid)))
            keys = []
        # 逐项过滤非法项
        clean_keys = []
        for idx, k in enumerate(keys or []):
            if not isinstance(k, str):
                findings.append(_warn("CONFIG", f"段落 {pid} keys[{idx}] 不是字符串，已忽略", tag=("para", pid)))
                continue
            kk = k.strip()
            if not kk:
                findings.append(_warn("CONFIG", f"段落 {pid} keys[{idx}] 为空字符串，已忽略", tag=("para", pid)))
                continue
            clean_keys.append(kk)
        task["keys"] = clean_keys  # 回填干净 keys，后续检查使用

    # 模板存在性
    tpl = config_dir / "template" / "report_template.docx"
    if not _exists(tpl):
        findings.append(_err("CONFIG", f"模板不存在：{tpl}", tag=("template", "report_template.docx")))

    return findings

def check_excel_alignment(sheet_cfg: dict, excel_sheets: list[str]) -> list[dict]:
    findings = []
    excel_set = set(excel_sheets or [])
    for sname in (sheet_cfg or {}).keys():
        if sname not in excel_set:
            findings.append(_warn("EXCEL", f"Excel 中不存在 Sheet：{sname}（将跳过）", tag=("sheet", sname)))
    return findings

def check_paragraph_keys(para_cfg: dict, sheet_cfg: dict) -> list[dict]:
    findings = []
    for pid, task in (para_cfg or {}).items():
        keys = task.get("keys", []) or []
        for k in keys:
            # 仅允许纯路径 "Sheet.Field"；不解析过滤器表达式
            if "." not in k or k.count(".") < 1:
                findings.append(_warn("KEY", f"{pid} 的 key 缺少 '.' 或格式不规范：{k}", tag=("para", pid)))
                continue
            parts = k.split(".", 1)
            sheet, field = parts[0], parts[1]
            if not sheet or not field:
                findings.append(_warn("KEY", f"{pid} 的 key 片段为空：{k}", tag=("para", pid)))
                continue
            if sheet not in (sheet_cfg or {}):
                findings.append(_err("KEY", f"{pid} 引用了未知 Sheet：{k}", tag=("para", pid)))
            else:
                declared = (sheet_cfg[sheet].get("keys", {}) or {})
                if field not in declared:
                    findings.append(_warn("KEY", f"{pid} 的字段不在 {sheet}.keys 声明中：{k}", tag=("para", pid)))
    return findings

def check_template_placeholders(config_dir: Path, sheet_cfg: dict, para_cfg: dict):
    """扫描模板占位符，并与配置交叉校验。"""
    placeholders = scan_placeholders(config_dir / "template" / "report_template.docx")
    findings = []

    variables_paths: set[str] = set()
    para_ids: set[str] = set()
    others: set[str] = set()

    for expr in placeholders:
        expr_str = expr.strip()
        var_paths = VAR_PATH_RE.findall(expr_str)

        if var_paths:
            for path in var_paths:
                variables_paths.add(path)
                sheet, field, *_ = path.split(".")
                if sheet not in (sheet_cfg or {}):
                    findings.append(_err("TEMPLATE", f"模板变量引用未知 Sheet：`{path}`", tag=("tpl-var", path)))
                elif field not in ((sheet_cfg or {}).get(sheet, {}).get("keys", {}) or {}):
                    findings.append(_warn("TEMPLATE", f"模板变量字段未在 keys 声明：`{path}`", tag=("tpl-var", path)))
            continue

        if SIMPLE_ID_RE.match(expr_str):
            para_ids.add(expr_str)
            if expr_str not in (para_cfg or {}):
                findings.append(_warn("TEMPLATE", f"模板段落占位符未在 paragraph_tasks 声明：`{expr_str}`", tag=("tpl-para", expr_str)))
            else:
                mode = (para_cfg[expr_str].get("mode") or ("generate" if "prompt" in para_cfg[expr_str] else "fill")).strip().lower()
                if mode != "generate":
                    findings.append(_warn("TEMPLATE", f"模板期望段落文本，但 `{expr_str}` 配置为 fill", tag=("tpl-para", expr_str)))
            continue

        others.add(expr_str)

    # 多余 generate 段落未在模板出现
    for pid, task in (para_cfg or {}).items():
        mode = (task.get("mode") or ("generate" if "prompt" in task else "fill")).strip().lower()
        if mode == "generate" and pid not in para_ids:
            findings.append(_warn("TEMPLATE", f"段落 `{pid}` 配置为 generate，但模板未使用该占位符", tag=("para", pid)))

    placeholder_info = {
        "variables": sorted(variables_paths),
        "paragraphs": sorted(para_ids),
        "others": sorted(others),
        "raw": placeholders,  # 已是干净表达式
    }
    return findings, placeholder_info

def check_naming_conflicts(sheet_cfg: dict, para_cfg: dict) -> list[dict]:
    """段落ID 与 Sheet 名冲突等命名风险。"""
    findings = []
    sheet_names = set((sheet_cfg or {}).keys())
    for pid in (para_cfg or {}).keys():
        if pid in sheet_names:
            findings.append(_warn("CONFIG", f"段落ID `{pid}` 与 Sheet 名同名，渲染时可能混淆命名空间", tag=("para", pid)))
    return findings
