# Agent Pipeline — Phase 3 设计规格

> Web UI + SSE 实时推送 + 操作日志 + Eclipse 熄灯

---

## 一、技术概览

```
agent-pipeline serve                 ← 新增命令
    │
    ▼
FastAPI (Python，和 pipeline 同进程)
    │
    ├─ POST  /run                 启动五 Agent 流水线
    ├─ GET   /stream/{id}         SSE 事件推送
    ├─ POST  /shutdown            优雅退出（Eclipse）
    ├─ GET   /                    静态页面 (index.html)
    └─ GET   /api/pipelines       历史流水线列表
```

事件源：PipelineLogHandler 双写 pipeline.log（持久化）+ asyncio.Queue（SSE 实时推）

---

## 二、新增/修改文件清单

| 文件 | 操作 | 说明 |
|------|:---:|------|
| `src/agent_pipeline/log_handler.py` | 新建 | PipelineLogHandler + 事件写函数 |
| `src/agent_pipeline/web/__init__.py` | 新建 | 包入口 |
| `src/agent_pipeline/web/server.py` | 新建 | FastAPI 应用 |
| `src/agent_pipeline/web/static/index.html` | 新建 | Web UI（复用 dashboard CSS） |
| `src/agent_pipeline/web/static/app.js` | 新建 | SSE 前端逻辑 |
| `src/agent_pipeline/web/static/styles.css` | 复制 | 从 agent-team-dashboard 搬 |
| `src/agent_pipeline/orchestrator.py` | 修改 | 7 个 node 注入 handler |
| `src/agent_pipeline/cli/main.py` | 修改 | 新增 `serve` 命令 |
| `requirements.txt` / `pyproject.toml` | 修改 | 加 fastapi + uvicorn + sse-starlette |

---

## 三、模块详设

### 3.1 PipelineLogHandler (`log_handler.py`, ~80 行)

```python
class PipelineLogHandler(BaseCallbackHandler):
    """LangChain callback — 同时写入 pipeline.log 和 asyncio.Queue"""
    
    def __init__(self, log_path: str, event_queue=None):
        self._log_path = log_path
        self._queue = event_queue      # None = CLI 模式（不推 SSE）
        self.current_agent = None       # orchestrator 在调 invoke 前设置
    
    def _emit(self, event: dict):
        line = json.dumps(event, ensure_ascii=False) + "\n"
        _write_line(self._log_path, line)          # 永远写文件
        if self._queue:
            try:
                self._queue.put_nowait(event)       # 有 SSE 才推
            except asyncio.QueueFull:
                pass                                 # 队列满不阻塞
    
    def on_llm_start(self, ...):   → emit({"event": "llm_start"})
    def on_tool_start(self, ...):  → emit({"event": "tool_start", "tool": ..., "input": ...})
    def on_tool_end(self, ...):    → emit({"event": "tool_end", "tool": ...})
    def on_llm_end(self, ...):     → emit({"event": "llm_end"})
```

**所有 emit 内 `try/except`——日志写失败不抛异常，不影响 pipeline 主流程。**

事件协议（与 SSE 一致）：

```json
{"time":"22:16:01","agent":"scout","event":"agent_start"}
{"time":"22:16:05","agent":"scout","event":"tool_start","tool":"search_web","input":"CLI TODO"}
{"time":"22:16:08","agent":"scout","event":"tool_end","tool":"search_web"}
{"time":"22:18:22","agent":"scout","event":"agent_end","status":"completed","duration_s":141}
{"time":"22:28:27","agent":null,"event":"pipeline_end","status":"completed","total_duration_s":746}
```

### 3.2 Orchestrator 修改（注入点）

每个 node 函数的三处修改（以 scout_node 为例）：

```python
def scout_node(state):
    # ① 节点开始前
    handler = _get_handler()        # 从 context 或全局获取 handler
    if handler:
        handler.current_agent = "scout"
        handler._emit({"time": now_iso(), "agent": "scout", "event": "agent_start"})
    
    t0 = time.time()
    # ... 原有逻辑不变 ...
    
    # ② agent.invoke 时传入 callbacks
    result = agent.invoke(
        {"messages": [...]},
        config={"callbacks": [handler]} if handler else None
    )
    
    # ③ 节点结束后
    if handler:
        handler._emit({"time": now_iso(), "agent": "scout", "event": "agent_end",
                       "status": entry["status"], "duration_s": int(time.time()-t0)})
```

**关键约束**：handler 通过全局变量 `_pipeline_handler` 存取。CLI 模式不设（保持现有行为），Web 模式在 `create_orchestrator` 调用前设置。

### 3.3 FastAPI 服务 (`web/server.py`, ~120 行)

```
端点：
  POST /run              → 后台线程跑 pipeline → 返回 pipeline_id
  GET  /stream/{id}      → SSE，从 asyncio.Queue 读事件 → 推给客户端
  POST /shutdown         → 杀 pipeline → server.close → process.exit(0)
  GET  /api/pipelines    → 返回历史 state.json 列表
  GET  /                 → 静态 index.html
  GET  /static/*         → 静态文件
```

**`/shutdown` 执行逻辑**：
1. 取消正在运行的 pipeline（ThreadPoolExecutor.cancel）
2. 写一条 `pipeline_end` 事件到日志
3. `uvicorn.Server.should_exit = True`
4. `os._exit(0)` — 确保所有线程立即退出

**`/stream/{id}` SSE 格式**：
```
data: {"time":"...","agent":"scout","event":"tool_start","tool":"search_web"}

data: {"time":"...","agent":"scout","event":"tool_end","tool":"search_web"}

```

每行 `data: {json}\n\n`，标准 SSE。

### 3.4 CLI `serve` 命令 (`cli/main.py` 新增)

```python
@cli.command()
@click.option("--port", default=3456, help="服务端口")
@click.option("--no-open", is_flag=True, help="不自动打开浏览器")
def serve(port: int, no_open: bool):
    """启动 Web 服务 + 打开浏览器"""
    import webbrowser
    if not no_open:
        webbrowser.open(f"http://localhost:{port}")
    import uvicorn
    uvicorn.run("agent_pipeline.web.server:app", host="0.0.0.0", port=port)
```

### 3.5 前端 (`static/` 三个文件)

**index.html** 骨架（复用 dashboard 布局）：
```
┌──────────────────────────────────────────────────────┐
│  ◈ Agent Pipeline           LIVE    ◉ Eclipse       │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌─ 输入区 ───────────────────────────────────────┐ │
│  │ [设计一个 CLI TODO 应用        ] [▶ 启动] [📋 示例] │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─ 流水线看板 ───────────────────────────────────┐ │
│  │                                                │ │
│  │  🔍 Scout    🎨 Designer  ⚙️ Builder           │ │
│  │  ✅ 142s     ✅ 89s       🔄 正在写代码...      │ │
│  │             🧪 Tester    📦 Seller              │ │
│  │             ⏳ 等待中     ⏳ 等待中              │ │
│  │                                                │ │
│  │  [████████████░░░░ 60%]                        │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─ 实时日志 ─────────────────────────────────────┐ │
│  │  22:16:05  Scout  → search_web("CLI TODO")      │ │
│  │  22:16:08  Scout  ← search_web 完成 (3.1s)     │ │
│  │  22:16:12  Scout  → read_url("https://...")     │ │
│  │  ...                                           │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─ 产出物 ───────────────────────────────────────┐ │
│  │  📄 scout→designer--调研报告.md (14.4 KB)       │ │
│  │  📄 designer→builder--需求分析.md (2.1 KB)      │ │
│  │  ...                                           │ │
│  └────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─ 帮助 ─────────────────────────────────────────┐ │
│  │  怎么用 · 事件说明 · 常见问题 · 环境变量        │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

**app.js** SSE 消费者核心逻辑：
```
1. 连 /stream/{id}
2. 事件 → 更新 Agent 卡片状态（idle/running/completed/failed）
3. 事件 → 追加实时日志行
4. agent_end → 更新卡片耗时 + 进度条
5. pipeline_end → 显示产出物列表 + 全部变灰
```

**styles.css**：从 agent-team-dashboard 的 `public/styles.css` 直接复制。新增：
- `.agent-card` — 五 Agent 卡片样式
- `.agent-card.running` — 蓝色边框 + 脉冲动画
- `.agent-card.completed` — 绿色勾
- `.agent-card.failed` — 红色边框 + 抖动
- `#eclipseBtn` — 熄灯按钮（同 dashboard 的 `#shutdownBtn` 样式）
- `.log-line` — 实时日志行

**帮助区内容**（index.html 内嵌）：
```
快速开始：
  1. 输入需求 → 点击 ▶ 启动
  2. 观察五 Agent 依次执行
  3. 完成后下载产出物

事件图例：
  🔵 agent_start   — Agent 开始工作
  🟢 agent_end     — Agent 完成（绿色 = 成功，红色 = 失败）
  🔧 tool_start    — 工具调用中
  ⚪ tool_end      — 工具返回

FAQ：
  Q: 需要什么环境？
  A: 只需设置 DEEPSEEK_API_KEY 环境变量

  Q: 流水线中途能停止吗？
  A: 点击右上角 ◉ Eclipse 停止并释放端口

  Q: 产出物在哪里？
  A: 命令行运行目录的 output/ 下
```

### 3.6 依赖变更

```
# pyproject.toml 新增
"fastapi>=0.100.0",
"uvicorn[standard]>=0.20.0",
"sse-starlette>=1.0.0",
```

---

## 四、实现顺序

| 步骤 | 内容 | 验证方式 |
|:---:|------|------|
| 1 | `log_handler.py` — PipelineLogHandler | 独立测试：写 handler → emit 事件 → 检查文件 |
| 2 | orchestrator 注入 — 7 个 node 加 handler | 跑一次 `run` → 检查 pipeline.log |
| 3 | `web/server.py` — FastAPI | `curl /api/pipelines` |
| 4 | CLI `serve` 命令 | `agent-pipeline serve --no-open` |
| 5 | 前端 — index.html + app.js + styles.css | 浏览器 `localhost:3456` |
| 6 | `/shutdown` | 启动 serve → 点 Eclipse → 确认端口释放 |
| 7 | 全流程测试 | `serve` → UI 输入需求 → 五 Agent 跑通 → Eclipse |

---

## 五、不改动的文件

- `orchestrator.py` 除了注入点，所有节点逻辑不变
- `agents/*.py` 完全不动
- `knowledge.py` / `models.py` / `state.py` 不动
- `test_cli.py` Phase 3 后由 Tester 更新
