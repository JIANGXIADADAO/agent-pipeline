"""Agent Pipeline Web 服务器 — FastAPI + SSE + Eclipse 熄灯。

端点:
  POST /run              启动流水线 → 返回 pipeline_id
  GET  /stream/{id}      SSE 事件流（实时推送）
  POST /shutdown         优雅退出（Eclipse 熄灯）
  GET  /api/pipelines    历史流水线列表
  GET  /                 静态首页 (index.html)
  GET  /static/*         静态资源
"""

import asyncio
import json
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from ..log_handler import PipelineLogHandler, now_iso

app = FastAPI(title="Agent Pipeline — Web UI")

# ---- 状态 ----
_active_pipelines: dict[str, dict] = {}  # pipeline_id -> {handler, queue, ...}
_pipeline_running = False
_start_time = time.time()

# ---- 静态文件 ----
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ============================================================
# 页面路由
# ============================================================

@app.get("/")
async def index():
    """返回 Web UI 首页。"""
    return FileResponse(os.path.join(_static_dir, "index.html"))


# ============================================================
# API 端点
# ============================================================

@app.post("/run")
async def run_pipeline(request: Request):
    """启动五 Agent 流水线（后台线程运行）。

    请求体: {"requirement": "用户需求文本"}
    返回: {"pipeline_id": "pl_20260610_143022_abc123"}
    """
    global _pipeline_running

    body = await request.json()
    requirement = body.get("requirement", "").strip()

    if not requirement:
        return JSONResponse(
            {"error": "需求不能为空。请提供有效的需求描述。"},
            status_code=400,
        )

    if _pipeline_running:
        return JSONResponse(
            {"error": "已有流水线在运行，请等待当前流水线完成。"},
            status_code=429,
        )

    pipeline_id = (
        f"pl_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    )

    # 创建事件队列和日志处理器
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    temp_log = os.path.join("output", "_logs", pipeline_id)
    os.makedirs(temp_log, exist_ok=True)
    log_path = os.path.join(temp_log, "pipeline.log")
    handler = PipelineLogHandler(log_path=log_path, event_queue=queue)

    # 注册活跃流水线
    _active_pipelines[pipeline_id] = {
        "handler": handler,
        "queue": queue,
        "log_path": log_path,
        "pipeline_id": pipeline_id,
    }
    _pipeline_running = True

    # 后台线程运行流水线
    def _run():
        global _pipeline_running
        try:
            from ..orchestrator import set_pipeline_handler, run_pipeline as _run_pipeline

            set_pipeline_handler(handler)
            state = _run_pipeline(requirement)

            handler._emit({
                "time": now_iso(),
                "agent": None,
                "event": "pipeline_end",
                "status": state.status,
            })
        except Exception as e:
            try:
                handler._emit({
                    "time": now_iso(),
                    "agent": None,
                    "event": "pipeline_end",
                    "status": "failed",
                    "error": str(e)[:200],
                })
            except Exception:
                pass
        finally:
            _pipeline_running = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"pipeline_id": pipeline_id}


@app.get("/stream/{pipeline_id}")
async def stream_events(pipeline_id: str):
    """SSE 事件流 — 从 asyncio.Queue 读取事件推送给客户端。"""
    pipeline = _active_pipelines.get(pipeline_id)
    if not pipeline:
        return JSONResponse({"error": "流水线不存在或已结束"}, status_code=404)

    queue = pipeline["queue"]

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield {"data": json.dumps(event, ensure_ascii=False)}

                    if event.get("event") == "pipeline_end":
                        # 延迟清理，让客户端收到最后一条事件
                        break
                except asyncio.TimeoutError:
                    # 发送 keepalive 保持连接
                    yield {"comment": "keepalive"}
                    # 检查流水线是否已结束或被清理
                    if pipeline_id not in _active_pipelines:
                        break
                    # 如果流水线不在运行但队列仍有数据，继续等待
                    if not _pipeline_running:
                        # 再试一次获取
                        continue
        finally:
            _active_pipelines.pop(pipeline_id, None)

    return EventSourceResponse(event_generator())


@app.post("/shutdown")
async def shutdown():
    """Eclipse 熄灯 — 优雅关闭服务器。

    1. 取消正在运行的流水线
    2. 写入 pipeline_end 事件
    3. 设置 should_exit
    4. os._exit(0)
    """
    # 向所有活跃流水线发送终止事件
    for pid, entry in list(_active_pipelines.items()):
        try:
            entry["handler"]._emit({
                "time": now_iso(),
                "agent": None,
                "event": "pipeline_end",
                "status": "cancelled",
            })
        except Exception:
            pass
    _active_pipelines.clear()

    # 先返回响应，再退出
    def _force_exit():
        time.sleep(0.3)
        os._exit(0)

    threading.Thread(target=_force_exit, daemon=True).start()

    return {"status": "eclipsed"}


@app.get("/api/pipelines")
async def api_pipelines():
    """返回历史流水线列表。"""
    from ..state import list_pipelines

    pipelines = list_pipelines(limit=20)
    return [
        {
            "pipeline_id": p.pipeline_id,
            "status": p.status,
            "project_slug": p.project_slug,
            "created_at": p.created_at[:19] if p.created_at else "",
            "requirement": p.requirement[:80],
        }
        for p in pipelines
    ]
