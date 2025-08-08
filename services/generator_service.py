# services/generator_service.py
from __future__ import annotations
from pathlib import Path
import logging, json, traceback

from agents.registry import get_generator
from utils.resolve import resolve, ensure_path_set

SYS_LOG  = logging.getLogger("system")
USER_LOG = logging.getLogger("user")
CFG_LOG  = logging.getLogger("config")

def run_generation_and_fill(para_cfg: dict, extracted: dict, plan: dict, ec, config_dir: Path) -> dict:
    gen_ctx: dict[str, str] = {}

    for pid, task in (para_cfg or {}).items():
        if pid in plan["paras_skip"]:
            SYS_LOG.warning(f"跳过存在问题的段落/占位符：{pid}")
            continue

        mode = task.get("mode") or ("generate" if "prompt" in task else "fill")
        keys = task.get("keys", [])

        try:
            missing = [k for k in (keys or []) if resolve(k, extracted, strict=True) is None]
            if mode == "generate" and missing:
                ec.add("warn", f"PARA:{pid}", f"缺字段 {missing}，已跳过生成")
                continue

            if mode == "generate":
                provider    = task.get("provider", "qwen")
                prompt_path = config_dir / "prompts" / task["prompt"]

                ctx_vals = {k: resolve(k, extracted, strict=True) for k in keys or []}
                CFG_LOG.debug(f"[GEN-VALUES] {pid}\n{json.dumps(ctx_vals, ensure_ascii=False, indent=2)}")

                generator = get_generator("GenericParagraphGenerator")(
                    prompt_path = prompt_path,
                    context     = extracted,   # 模板里 {{ Sheet.Field }}
                    config_dir  = config_dir,
                    provider    = provider,
                    paragraph_id= pid,
                )
                text = generator.generate()
                gen_ctx[pid] = text
                USER_LOG.info(f"[生成完成] {pid}：{(text[:200] + '...') if len(text)>200 else text}")

            else:  # fill
                for miss in missing:
                    ensure_path_set(extracted, miss, "-")
                    ec.add("warn", f"FILL:{pid}", f"缺字段 {miss}，已用默认 '-' 补位")

                if keys:
                    val_map = {k: resolve(k, extracted, strict=False, default="-") for k in keys}
                    CFG_LOG.debug(f"[FILL-VALUES] pid={pid}\n{json.dumps(val_map, ensure_ascii=False, indent=2)}")
                    summary = ", ".join(f"{k}={val_map[k]}" for k in val_map)
                    USER_LOG.info(f"[直填值] {pid} → {summary[:500] + ' ...' if len(summary)>500 else summary}")
                else:
                    SYS_LOG.info(f"[直填变量] {pid}（未声明 keys，跳过值记录）")

        except Exception as e:
            ec.add("error", f"PARA:{pid}", f"处理失败（mode={mode}）：{e}", traceback.format_exc())
            continue

    return gen_ctx
