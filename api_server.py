from __future__ import annotations
import os, io, uuid, traceback, json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, Future

from fastapi import FastAPI, HTTPException, Body, Query
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse
from pydantic import BaseModel, Field

# ==== 引擎模块（来自你的项目） ====
from orchestrator import run_pipeline
from validator.validate import validate_configs
from validator.report import write_report_files
from io_utils.loaders import load_excel_first

# -------------------- 配置 --------------------
API_MAX_WORKERS = int(os.getenv("API_MAX_WORKERS", "4"))
WORKSPACES_ROOT = os.getenv("WORKSPACES_ROOT")  # 可选：限制所有项目必须在这个根目录下
# ------------------------------------------------

app = FastAPI(title="Report Pipeline API", version="1.0.0")
EXECUTOR = ThreadPoolExecutor(max_workers=API_MAX_WORKERS)

# ---- 内存作业表 ----
JOBS: Dict[str, Dict[str, Any]] = {}  # job_id -> info
FUTURES: Dict[str, Future] = {}

# -------------------- 数据模型 --------------------
class ProjectRef(BaseModel):
    workspace_path: str = Field(..., description="服务器本地工作区根目录（私有云同步到本地的位置）")
    project_rel_path: str = Field(..., description="工作区下的项目相对路径，例如 teamA/proj_2025_08")

class ValidateRequest(ProjectRef):
    simulate_render: bool = Field(True, description="是否在验证阶段执行模板模拟渲染（StrictUndefined）")
    strict: bool = Field(False, description="是否严格模式（仅用于报告标记，API行为不受影响）")

class RunRequest(ProjectRef):
    report_name: str = Field("生成报告文件", description="输出 docx 文件名（不带扩展名）")

# -------------------- 工具函数 --------------------
def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def resolve_project_root(workspace_path: str, project_rel_path: str) -> Path:
    """
    把 workspace + 相对路径拼成项目根路径，并做穿越防护：
    - 规范化（resolve）
    - 必须在 WORKSPACES_ROOT 内（如果配置了）
    """
    ws = Path(workspace_path).expanduser().resolve()
    pr = (ws / project_rel_path).resolve()
    if WORKSPACES_ROOT:
        wr = Path(WORKSPACES_ROOT).expanduser().resolve()
        if not pr.is_relative_to(wr):
            raise HTTPException(status_code=400, detail=f"project path must be under WORKSPACES_ROOT: {wr}")
    if not pr.is_relative_to(ws):
        raise HTTPException(status_code=400, detail="project path traversal detected")
    return pr

def ensure_project_layout(project_root: Path) -> dict:
    """
    检查项目结构，返回关键路径；缺失时抛 HTTPException。
    """
    configs = project_root / "configs"
    logs    = project_root / "logs"
    if not configs.exists():
        raise HTTPException(status_code=400, detail=f"configs not found: {configs}")
    (logs).mkdir(parents=True, exist_ok=True)
    # 可选：做一些软校验提醒
    bc = configs / "business_configs"
    tpl = configs / "template" / "report_template.docx"
    hints = []
    if not bc.exists():
        hints.append("business_configs missing")
    if not tpl.exists():
        hints.append("template/report_template.docx missing")
    return {"config_dir": configs, "logs_dir": logs, "hints": hints}

def scan_latest_docx(output_dir: Path) -> Optional[Path]:
    files = sorted(output_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None

def tail_file(path: Path, lines: int = 200) -> str:
    if not path.exists():
        return ""
    # 简单安全的 tail（适合中小日志）
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        data = f.read().splitlines()
        return "\n".join(data[-lines:])

def job_status(job_id: str) -> Dict[str, Any]:
    if job_id not in JOBS:
        raise HTTPException(404, "job not found")
    info = JOBS[job_id]
    # 更新 Future 状态
    fut = FUTURES.get(job_id)
    if fut and info["status"] in ("queued", "running"):
        if fut.done():
            exc = fut.exception()
            info["ended_at"] = _now()
            if exc:
                info["status"] = "failed"
                info["error"]  = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            else:
                info["status"] = "succeeded"
    return info

# -------------------- 验证（同步） --------------------
@app.post("/validate")
def validate_endpoint(req: ValidateRequest):
    """
    验证配置/模板/Excel是否匹配，不调用 LLM、不产出文档。
    - 占位符解析为干净表达式
    - 可选：StrictUndefined 的模板模拟渲染（提前发现未定义变量/语法错误）
    - 报告写入 <project_root>/logs/validator_report.json|md
    """
    project_root = resolve_project_root(req.workspace_path, req.project_rel_path)
    paths = ensure_project_layout(project_root)
    config_dir = paths["config_dir"]

    # 读取 Excel（取第一个 *.xls*）
    xls = None
    try:
        xls = load_excel_first(config_dir / "input")
    except Exception as e:
        # Excel 缺失不抛死，交给验证器记录警告/错误
        xls = None

    # 验证（不写 docx、不调 LLM）
    report = validate_configs(config_dir, xls, simulate_render=req.simulate_render)
    # 写报告到 logs/
    write_report_files(report, project_root)

    return {
        "project": str(project_root),
        "severity": report.get("severity"),
        "planned_skips": report.get("planned_skips"),
        "placeholders": report.get("placeholders"),
        "simulate": report.get("simulate"),
        "report_paths": {
            "json": str(project_root / "logs" / "validator_report.json"),
            "md": str(project_root / "logs" / "validator_report.md"),
        },
        "hints": paths["hints"],
    }

# -------------------- 运行（异步作业） --------------------
@app.post("/run")
def run_endpoint(req: RunRequest):
    """
    异步启动一次报告生成：抽取 → 生成/直填 → 渲染 Word。
    - 日志、运行摘要写入 <project_root>/logs/
    - 产物写入 <project_root>/configs/output/
    """
    project_root = resolve_project_root(req.workspace_path, req.project_rel_path)
    paths = ensure_project_layout(project_root)
    config_dir = paths["config_dir"]

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "job_id": job_id,
        "type": "run",
        "status": "queued",
        "project_root": str(project_root),
        "started_at": None,
        "ended_at": None,
        "error": None,
        "artifacts": {"docx": None},
    }

    def _task():
        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["started_at"] = _now()
        try:
            # 关键：把 root 指到项目根，这样你的引擎就会把 logs 写到 <project_root>/logs/
            run_pipeline(config_dir=config_dir, report_name=req.report_name, root=project_root)
            # 找产物
            out = scan_latest_docx(config_dir / "output")
            JOBS[job_id]["artifacts"]["docx"] = str(out) if out else None
        except Exception as e:
            JOBS[job_id]["error"]  = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            raise
        finally:
            JOBS[job_id]["ended_at"] = _now()

    fut = EXECUTOR.submit(_task)
    FUTURES[job_id] = fut

    return {"job_id": job_id, "status": "queued", "project_root": str(project_root)}

# -------------------- 作业状态 --------------------
@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    return job_status(job_id)

# -------------------- 拉取日志尾部 --------------------
@app.get("/jobs/{job_id}/logs", response_class=PlainTextResponse)
def get_logs(job_id: str,
             kind: str = Query("user", regex="^(user|system|config|exec)$"),
             tail: int = Query(200, ge=1, le=5000)):
    info = job_status(job_id)
    project_root = Path(info["project_root"])
    logs_dir = project_root / "logs"
    fname = {
        "user":   "user.log",
        "system": "system.log",
        "config": "config.log",
        "exec":   "exec.log",  # 预留：如果未来你用子进程跑 main.py，可把 stdout/stderr 写到 exec.log
    }[kind]
    content = tail_file(logs_dir / fname, lines=tail)
    return content or "(empty)"

# -------------------- 下载产物 --------------------
@app.get("/jobs/{job_id}/artifact")
def get_artifact(job_id: str):
    info = job_status(job_id)
    path = info.get("artifacts", {}).get("docx")
    if not path:
        raise HTTPException(404, "artifact not ready")
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "artifact missing on disk")
    return FileResponse(p, filename=p.name, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# -------------------- 拉取报告（验证 & 运行摘要） --------------------
@app.get("/jobs/{job_id}/reports")
def get_reports(job_id: str):
    info = job_status(job_id)
    project_root = Path(info["project_root"])
    logs_dir = project_root / "logs"

    out: Dict[str, Any] = {}
    vr = logs_dir / "validator_report.json"
    rs = logs_dir / "run_summary.json"
    if vr.exists():
        try:
            out["validator_report"] = json.loads(vr.read_text(encoding="utf-8"))
        except Exception:
            out["validator_report"] = {"_error": "failed to parse validator_report.json"}
    if rs.exists():
        try:
            out["run_summary"] = json.loads(rs.read_text(encoding="utf-8"))
        except Exception:
            out["run_summary"] = {"_error": "failed to parse run_summary.json"}
    if not out:
        raise HTTPException(404, "no reports found")
    return JSONResponse(out)

# -------------------- 健康检查 --------------------
@app.get("/healthz")
def healthz():
    return {"ok": True, "workers": API_MAX_WORKERS}

# -------------------- 启动 --------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
