import os, logging
from jinja2 import Template
from agents.registry import register_generator
from llm_client import apply_provider
from logging.handlers import TimedRotatingFileHandler

# -------------------- 日志兜底初始化（仅当外部未配置时） --------------------
def _setup_default_logging():
    if logging.getLogger("system").handlers:
        return
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    def _mk(name, filename, level, to_console=False):
        logger = logging.getLogger(name)
        logger.setLevel(level)
        fh = TimedRotatingFileHandler(logs_dir / filename, when="midnight", backupCount=14, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        if to_console:
            ch = logging.StreamHandler()
            ch.setFormatter(fmt)
            ch.setLevel(level)
            logger.addHandler(ch)
        logger.propagate = False
        return logger

    _mk("user",   "user.log",   logging.INFO)
    _mk("system", "system.log", logging.INFO, to_console=True)
    _mk("config", "config.log", logging.DEBUG)

_setup_default_logging()
USER_LOG   = logging.getLogger("user")
SYS_LOG    = logging.getLogger("system")
CONFIG_LOG = logging.getLogger("config")
# -----------------------------------------------------------------------

def _truncate(txt: str, limit: int = 16000) -> str:
    return txt if len(txt) <= limit else (txt[:limit] + "\n...[truncated]")

@register_generator
class GenericParagraphGenerator:
    """
    prompt_path + context  → 段落文本
    """

    def __init__(self, prompt_path: str, context: dict, provider: str | None = None, config_dir: str = "", paragraph_id: str | None = None):
        self.prompt_path  = prompt_path
        self.context      = context                 # 这里通常是 extracted（变量命名空间）
        self.paragraph_id = paragraph_id or "UNKNOWN"
        provider          = provider or os.getenv("LLM_PROVIDER", "openai")
        self.client, self.model_name = apply_provider(provider, config_dir)

    # ---------- core ----------
    def generate(self) -> str:
        prompt = Template(open(self.prompt_path, encoding="utf-8").read()).render(**self.context)

        # ✅【配置级】记录融合后的生成 Prompt
        CONFIG_LOG.debug(f"[GEN-PROMPT] pid={self.paragraph_id}, model={self.model_name}\n{_truncate(prompt)}")

        SYS_LOG.info(f"调用生成 LLM：pid={self.paragraph_id}, model={self.model_name}")  # 【系统级】

        resp = self.client.chat.completions.create(
            model    = self.model_name,
            messages = [{"role": "system", "content": prompt}]
        )
        text = resp.choices[0].message.content.strip()

        # ✅【配置级】记录完整生成文本
        CONFIG_LOG.debug(f"[GEN-TEXT] pid={self.paragraph_id}\n{_truncate(text)}")

        # ✅【用户级】记录摘要（前 200 字）
        USER_LOG.info(f"[生成完成] {self.paragraph_id}：{(text[:200] + '...') if len(text)>200 else text}")
        return text
