# io_utils/loaders.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Any
import logging
import yaml
import pandas as pd

SYS_LOG = logging.getLogger("system")

# ---------------- 宽松 YAML 加载（运行期用） ----------------
def load_yaml(path: Path) -> dict:
    """
    宽松加载：用于运行期（保持原有行为）。
    解析失败抛出 yaml.YAMLError，让上层去捕获。
    """
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

# ---------------- 严格 YAML 加载（验证器用，含重复键检测） ----------------
class _DupLoader(yaml.SafeLoader):
    pass

def _construct_mapping_with_dups(loader: _DupLoader, node: yaml.nodes.MappingNode, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key_obj = loader.construct_object(key_node, deep=deep)
        key_repr = str(key_obj)
        if key_repr in mapping:
            if not hasattr(loader, "_duplicate_keys"):
                loader._duplicate_keys = []
            mark = getattr(key_node, "start_mark", None)
            where = f"{mark.name}:{mark.line+1}" if mark else "unknown"
            loader._duplicate_keys.append({"key": key_repr, "where": where})
        mapping[key_repr] = loader.construct_object(value_node, deep=deep)
    return mapping

_DupLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_with_dups
)

def load_yaml_strict(path: Path) -> Tuple[dict, list[dict], str | None]:
    """
    返回 (data, duplicates, error)
    - data: 解析结果（失败时为空 dict）
    - duplicates: [{'key': 'xxx', 'where': 'file:line'}, ...]
    - error: 解析错误消息（None 表示无错）
    """
    try:
        with open(path, encoding="utf-8") as f:
            loader = _DupLoader(f)
            data = loader.get_single_data()
            dups = getattr(loader, "_duplicate_keys", [])
            return (data or {}, dups, None)
    except yaml.YAMLError as e:
        return ({}, [], f"YAML parse error in {path}: {e}")
    except FileNotFoundError:
        return ({}, [], f"YAML not found: {path}")

# ---------------- Excel / 模板加载（向后兼容 + 小幅增强） ----------------
def load_excel_first(input_dir: Path, pattern: str = "*.xls*") -> pd.ExcelFile:
    """
    在 input_dir 中按 pattern 找到第一个 Excel，并返回 pd.ExcelFile。
    - 找不到：抛 FileNotFoundError（保持原行为）
    - 多个：记录 system 日志 warning，但仍返回第一个（字典序）
    - 打开失败：抛 ValueError，附带更清晰的错误信息
    """
    input_dir = Path(input_dir)
    matches = sorted(input_dir.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"目录 {input_dir} 下没有找到任何 {pattern} 文件！")
    if len(matches) > 1:
        SYS_LOG.warning(f"发现 {len(matches)} 个 Excel，仅使用第一个：{matches[0].name}")
    try:
        return pd.ExcelFile(matches[0])
    except Exception as e:
        # 给出更友好的错误提示
        raise ValueError(f"无法打开 Excel 文件：{matches[0]}（可能已损坏或格式不受支持）。原始错误：{e}") from e

def load_template_exists(config_dir: Path) -> Path:
    """
    检查模板是否存在；存在则返回其路径。
    - 不存在：抛 FileNotFoundError（保持原行为）
    - 若路径是目录或扩展名错误：抛 FileNotFoundError，提示不合法
    """
    p = Path(config_dir) / "template" / "report_template.docx"
    if not p.exists() or p.is_dir() or p.suffix.lower() != ".docx":
        raise FileNotFoundError(f"模板不存在或非法：{p}")
    return p
