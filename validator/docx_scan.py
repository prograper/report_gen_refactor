# validator/docx_scan.py
from __future__ import annotations
from pathlib import Path
import zipfile
import re
from xml.etree import ElementTree as ET

# 匹配 {{ ... }}，只抓内部表达式（跨行也行）
JINJA_RE = re.compile(r"{{\s*(.+?)\s*}}", flags=re.DOTALL)

def _read_xml_text_ordered(z: zipfile.ZipFile, member: str) -> str:
    """把指定部件（document/header/footer）里的 <w:t> 文本按出现顺序拼接成纯文本。"""
    try:
        with z.open(member) as f:
            xml = f.read()
    except KeyError:
        return ""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        # 兜底：解析失败就退化为原字节解码（极少发生）
        return xml.decode("utf-8", errors="ignore")

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    texts = []
    for t in root.findall(".//w:t", ns):
        # 注意 w:t 可能带 xml:space="preserve"，这里保留原文本
        texts.append(t.text or "")
    return "".join(texts)

def scan_placeholders(docx_path: Path) -> list[str]:
    """
    扫描 docx 中的 Jinja 占位符，返回“花括号内部”的干净表达式列表。
    - 先把 document.xml / 所有 header*.xml / footer*.xml 的 <w:t> 合并成纯文本
    - 再用正则抓 {{ ... }}，不包含任何 XML 片段
    """
    if not docx_path.exists():
        return []

    pure_texts = []
    with zipfile.ZipFile(docx_path, "r") as z:
        # 主文档
        pure_texts.append(_read_xml_text_ordered(z, "word/document.xml"))
        # 所有页眉/页脚
        for name in z.namelist():
            if name.startswith("word/header") and name.endswith(".xml"):
                pure_texts.append(_read_xml_text_ordered(z, name))
            if name.startswith("word/footer") and name.endswith(".xml"):
                pure_texts.append(_read_xml_text_ordered(z, name))

    full_text = "\n".join(pure_texts)
    matches = [m.group(1).strip() for m in JINJA_RE.finditer(full_text)]
    # 去重但保持稳定顺序
    seen = set()
    ordered_unique = []
    for m in matches:
        if m not in seen:
            seen.add(m)
            ordered_unique.append(m)
    return ordered_unique
