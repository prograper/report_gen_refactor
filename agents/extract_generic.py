from pathlib import Path
import json, os, pandas as pd, logging
from jinja2 import Template
from agents.registry import register_extractor
from llm_client import apply_provider
from logging.handlers import TimedRotatingFileHandler

# -------------------- 日志兜底初始化（仅当外部未配置时） --------------------
def _setup_default_logging():
    # 如果系统日志已有 handler，说明主程序已配置；跳过兜底
    if logging.getLogger("system").handlers:
        return
    root = Path(__file__).resolve().parents[1]   # 项目根目录（agents 的上一级）
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

TYPE_MAP = {
    "number": {"type": "number"},
    "string": {"type": "string"},
    "array[string]": {"type": "array", "items": {"type": "string"}},
}

def df_to_text(df: pd.DataFrame) -> str:
    return df.to_csv(index=False)

def _truncate(txt: str, limit: int = 4000) -> str:
    return txt if len(txt) <= limit else (txt[:limit] + "\n...[truncated]")

def _pp_json(obj, limit: int = 20000) -> str:
    """美化 JSON 并带最大长度限制，避免日志爆表"""
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2)
    except Exception:
        s = str(obj)
    return s if len(s) <= limit else s[:limit] + "\n...[truncated]"

def _kv_summary(d: dict, maxlen: int = 300) -> str:
    """将 {a:1,b:2,...} 压成 "a=1, b=2, ..."，并控制最大长度"""
    parts = [f"{k}={d[k]}" for k in d]
    line = ", ".join(parts)
    if len(line) <= maxlen:
        return line
    keep = []
    for p in parts:
        if len(", ".join(keep + [p])) > maxlen:
            break
        keep.append(p)
    rest = max(0, len(parts) - len(keep))
    return ", ".join(keep) + (f" ... (+{rest})" if rest else "")

@register_extractor
class GenericExtractor:
    """
    DataFrame + prompt + keys  →  JSON
    provider 缺省看环境变量 LLM_PROVIDER，默认 openai
    """

    def __init__(
        self,
        df,
        keys: dict,
        prompt_path: str | Path,
        provider: str | None = None,
        config_dir: Path = Path(""),
        sheet_name: str | None = None,          # ← 便于日志标注
    ):
        self.df          = df
        self.keys        = keys
        self.prompt_path = Path(prompt_path)
        self.sheet_name  = sheet_name or "UNKNOWN"
        provider         = provider or os.getenv("LLM_PROVIDER", "openai")
        self.client, self.model_name = apply_provider(provider, config_dir)

    # ---------- helpers ----------
    def _build_schema(self):
        props = {k: TYPE_MAP.get(t, {"type": "string"}) for k, t in self.keys.items()}
        return {
            "name": "extract",
            "parameters": {"type": "object",
                           "properties": props,
                           "required": list(props)}
        }

    def _render_prompt(self) -> str:
        tpl = Template(self.prompt_path.read_text(encoding="utf-8"))
        return tpl.render(table=df_to_text(self.df), keys=list(self.keys))

    # ---------- public ----------
    def extract(self) -> dict:
        prompt  = self._render_prompt()
        schema  = self._build_schema()

        # 【配置级】记录融合后的提示词 & Schema（注意可能包含敏感数据）
        CONFIG_LOG.debug(f"[EXTRACT-PROMPT] sheet={self.sheet_name}, model={self.model_name}\n{_truncate(prompt)}")
        CONFIG_LOG.debug(f"[EXTRACT-SCHEMA]  sheet={self.sheet_name} keys={list(self.keys)} schema={schema}")

        tools = [{"type": "function", "function": schema}]
        tool_choices = {"type": "function", "function": {"name": "extract"}}

        SYS_LOG.info(f"调用抽取 LLM：sheet={self.sheet_name}, model={self.model_name}")  # 【系统级】

        resp = self.client.chat.completions.create(
            model        = self.model_name,
            messages     = [{"role": "system", "content": prompt}],
            tools        = tools,
            tool_choice  = tool_choices,
        )

        # 返回第一个工具调用的参数
        if resp.choices[0].message.tool_calls:
            for tool_call in resp.choices[0].message.tool_calls:
                arguments = json.loads(tool_call.function.arguments)

                # ✅【配置级】记录“完整变量值 JSON”
                CONFIG_LOG.debug(f"[EXTRACT-VALUES] sheet={self.sheet_name}\n{_pp_json(arguments)}")

                # ✅【用户级】记录“变量摘要”便于快速查阅
                USER_LOG.info(f"[抽取完成] {self.sheet_name} → {_kv_summary(arguments)}")
                return arguments

        # 若没有 tool_calls（极少见），给出系统日志
        SYS_LOG.warning(f"抽取无返回 tool_calls：sheet={self.sheet_name}")
        return {}
