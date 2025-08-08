# llm_client.py
import os, yaml, openai
from pathlib import Path

# provider → (client, model_name)
_clients: dict[str, tuple[openai.OpenAI, str]] = {}

def apply_provider(name: str = "openai", config_dir: Path = Path("")) -> tuple[openai.OpenAI, str]:
    _CFG = yaml.safe_load((config_dir / "business_configs" / "llm.yaml").read_text(encoding="utf-8"))
    """
    返回 (client, model_name) 供调用。
    - client  已按 base_url / key / extra 初始化
    - model_name  从 llm.yaml 读
    结果会缓存在 _clients，重复调用不再重新建连接。
    """
    if name in _clients:
        return _clients[name]

    if name not in _CFG:
        raise KeyError(f"provider {name!r} not in {config_dir.name}/configs/llm.yaml")

    cfg       = _CFG[name]
    api_key   = os.getenv(cfg["key_env"], "")
    base_url  = cfg.get("base_url")
    extra     = cfg.get("extra", {})

    client = openai.OpenAI(api_key=api_key, base_url=base_url, **extra)
    _clients[name] = (client, cfg["model_name"])
    print(f"✓ LLM provider loaded: {name} ({cfg['model_name']})")
    return _clients[name]
