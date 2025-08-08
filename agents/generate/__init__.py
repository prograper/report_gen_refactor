# agents/generate/__init__.py
# 只负责触发注册：导入 base 即会执行 @register_generator
from .base import GenericParagraphGenerator  # noqa: F401

__all__ = ["GenericParagraphGenerator"]
