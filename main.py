# main.py
from __future__ import annotations
import os, sys, argparse, logging
from pathlib import Path

from core.logging_setup import setup_logging  # 你已有 logging_setup.py；若路径不同请调整
from validator.validate import validate_configs_cli
from orchestrator import run_pipeline

ROOT = Path(__file__).parent

def parse_args():
    ap = argparse.ArgumentParser(description="Pharma Report Pipeline")
    sub = ap.add_subparsers(dest="cmd")

    # validate 子命令
    ap_val = sub.add_parser("validate", help="只验证配置/模板/Excel是否匹配，不调用LLM/不产出docx")
    ap_val.add_argument("-c", "--config", default="configs", help="配置目录（含 business_configs/、prompts/、template/）")
    ap_val.add_argument("-i", "--input",  default=None, help="Excel 文件路径（默认读取 config/input 下的第一个）")
    ap_val.add_argument("--no-render", action="store_true", help="不做模板模拟渲染")
    ap_val.add_argument("--strict", action="store_true", help="严格模式：存在 error 则退出码为1")

    # run 子命令（兼容之前的参数）
    ap_run = sub.add_parser("run", help="执行流水线：抽取→生成/直填→渲染docx")
    ap_run.add_argument("-c", "--config", default="configs", help="配置目录")
    ap_run.add_argument("-n", "--name", default="生成报告文件", help="输出报告名称（不含扩展名）")

    # 向后兼容：未给子命令时默认 run
    ap.add_argument("-C", "--compat-config", dest="compat_config", default=None, help=argparse.SUPPRESS)
    ap.add_argument("-N", "--compat-name",   dest="compat_name",   default=None, help=argparse.SUPPRESS)
    return ap.parse_args()

def main():
    args = parse_args()
    setup_logging(ROOT)

    if args.cmd == "validate":
        exit_code = validate_configs_cli(
            config_dir=Path(args.config),
            excel_path=Path(args.input) if args.input else None,
            simulate_render=not args.no_render,
            strict=args.strict,
            root=ROOT,
        )
        sys.exit(exit_code)

    # 兼容旧调用：python main.py -c ... -n ...
    if args.compat_config or args.compat_name:
        config_dir = args.compat_config or "configs"
        name       = args.compat_name   or "生成报告文件"
        run_pipeline(Path(config_dir), name, root=ROOT)
        return

    # 正常 run 子命令
    if args.cmd == "run" or args.cmd is None:
        run_pipeline(Path(args.config), args.name, root=ROOT)
    else:
        logging.getLogger("system").error(f"未知命令：{args.cmd}")
        sys.exit(2)

if __name__ == "__main__":
    if "DASHSCOPE_API_KEY" not in os.environ:
        logging.getLogger("system").error("缺少 DASHSCOPE_API_KEY 环境变量")
        sys.exit("✗ 请先 set DASHSCOPE_API_KEY=sk-...")
    main()
