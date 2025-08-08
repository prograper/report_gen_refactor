# agents/__init__.py
"""
导入所有带注册装饰器的模块，以确保类在 Registry 中注册
"""
# 注册 GenericExtractor
from . import extract_generic  # noqa: F401
# 注册 GenericParagraphGenerator（通过 generate/__init__.py 间接导入 base）
from . import generate  # noqa: F401
