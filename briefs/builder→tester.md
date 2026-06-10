# Agent Pipeline — Builder → Tester 交接

> 此文档记录 Builder 实现过程中与 Designer 规格的偏差、已知局限和测试注意事项。

---

## 一、实现总结

### Phase 1 已实现模块

| 模块 | 文件 | 状态 |
|------|------|:----:|
| 数据模型 | `src/agent_pipeline/models.py` | ✅ |
| 状态持久化 | `src/agent_pipeline/state.py` | ✅ |
| 预索引门控 RAG | `src/agent_pipeline/knowledge.py` | ✅ |
| Scout Agent | `src/agent_pipeline/agents/scout.py` | ✅ |
| Orchestrator | `src/agent_pipeline/orchestrator.py` | ✅ |
| CLI 入口 | `src/agent_pipeline/cli/main.py` | ✅ |

### 文件结构

```
src/agent_pipeline/
├── __init__.py          # 版本号
├── models.py            # PipelineState, AgentOutput
├── state.py             # state.json 读写 + 历史管理
├── knowledge.py         # 预索引门控 RAG（index.md 子串匹配）
├── orchestrator.py      # run_pipeline() 直线流程
├── agents/
│   ├── __init__.py
│   └── scout.py         # create_react_agent + 4 工具
└── cli/
    ├── __init__.py
    └── main.py          # Click CLI: run / status / list
```

---

## 二、与 Designer 规格的偏差

### 偏差 B01：search_web 使用 DuckDuckGo HTML 搜索（无 API Key）

**Designer 规格**：未指定搜索引擎，要求使用 httpx。

**实现**：使用 DuckDuckGo HTML 搜索（`html.duckduckgo.com/html/`），以 POST 表单方式提交查询，BeautifulSoup 解析 HTML 结果。不需要 API Key。

**原因**：
- DuckDuckGo 免费，无需注册/API Key，降低用户上手门槛
- httpx + BeautifulSoup 已在依赖清单中，不需要额外引入

**已知问题**：
- DuckDuckGo 可能对频繁请求限流（Rate limit）
- 搜索结果 HTML 结构可能随 DuckDuckGo 更新而变化
- 不适合高频调用（建议 Phase 2 后接入 SerpAPI / Google Search API）

### 偏差 B02：index.md 路径使用相对路径 + 环境变量覆盖

**Designer 规格**：`index_path="wiki/index.md"`（硬编码相对路径）

**实现**：默认路径 `../../wiki/`（相对项目根目录），可通过 `AGENT_PIPELINE_WIKI_PATH` 环境变量覆盖。

**原因**：
- `wiki/` 目录在项目根目录的上级两级（`../../wiki/`），硬编码 `wiki/index.md` 会找不到文件
- 环境变量覆盖支持在不同工作目录下运行

### 偏差 B03：项目名称提取使用启发式规则而非 LLM

**Designer 规格**：`extract_project_name(requirement)` 未指定实现方式

**实现**：使用正则移除常见中文前缀动词（"调研"、"分析"、"研究"等），取前 40 字符。

**原因**：
- 避免在 Phase 1 引入不必要的 LLM 调用
- 启发式规则足够处理大部分自然语言需求
- 后续可升级为 LLM 提取

### 偏差 B04：Agent 超时使用 ThreadPoolExecutor 而非 asyncio

**Designer 规格**：Agent 超时 5 分钟自动重试

**实现**：使用 `concurrent.futures.ThreadPoolExecutor` + `future.result(timeout=300)` 实现超时控制。

**原因**：
- `create_react_agent().invoke()` 是同步阻塞调用，无法直接设置超时
- ThreadPoolExecutor 提供了最简洁的超时包装方式
- Phase 2 升级为异步时改为 asyncio

### 偏差 B05：没有创建 agents/templates/scout.template.md 模板文件

**Designer 规格**：System Prompt 从 `agents/templates/scout.template.md` 提取

**实现**：System Prompt 直接在 `agents/scout.py` 的 `_get_system_prompt()` 函数中定义。

**原因**：
- Phase 1 只有一个 Agent，模板文件尚未创建
- `agents/templates/` 目录在项目根目录，不属于 Builder 的写入范围
- 后续可以提取到独立模板文件

### 偏差 B06：--resume 功能简化实现

**Designer 规格**：`agent-pipeline run --resume` 支持断点恢复

**实现**：--resume 会查找最新未完成的流水线并重新执行 Scout Agent。Phase 1 只有单个 Agent，resume 的实际效果是重新运行。

**原因**：
- Phase 1 单 Agent 场景下 resume 价值有限
- 完整的 resume 需要 Phase 2 多 Agent + Checkpoint 支持

### 偏差 B07：write_report 工具使用工厂模式绑定 context_dir

**Designer 规格**：write_report(path, content) 直接接收路径

**实现**：使用 `_make_write_report(context_dir)` 工厂函数创建绑定 `context_dir` 的工具实例，并提供路径逃逸安全检查。

**原因**：
- LangChain 工具在创建时绑定，Agent 运行时无法动态设置 context_dir
- 路径逃逸检查增强了安全性

---

## 三、已知局限

### L01：搜索依赖 DuckDuckGo HTML 接口

DuckDuckGo HTML 接口不是官方搜索 API，可能随时变更或限流。建议 Phase 2 接入付费搜索 API。

### L02：知识库匹配是简单子串匹配

Phase 1 的预索引 RAG 只做关键词子串匹配，不支持语义搜索。中文分词效果有限（单个汉字也可能匹配）。Phase 3 会升级为 pgvector 向量检索。

### L03：Agent 执行进度不可见

CLI 在 Agent 执行期间没有实时进度输出（Agent 的 ReAct 循环过程不对外暴露）。用户只能看到开始和结束。Phase 2 SSE 推送会解决。

### L04：无并发流水线支持

Phase 1 是单线程串行执行。运行多个流水线需要排队。

### L05：无取消流水线机制

启动后的流水线无法通过 CLI 取消（没有 `agent-pipeline stop` 命令）。

---

## 四、Tester 测试建议

### 4.1 正向功能测试

| ID | 场景 | 预期 |
|----|------|------|
| T1 | 标准需求 | `agent-pipeline run "调研 AI 编码助手市场"` → 输出报告 |
| T2 | 空需求 | `agent-pipeline run ""` → 报错"需求不能为空" |
| T3 | 无 API Key | 取消 ANTHROPIC_API_KEY → 报错提示设置 |
| T4 | 短需求 | `agent-pipeline run "分析竞品"` → 正常运行 |
| T5 | CLI --help | `agent-pipeline --help` → 显示帮助信息 |

### 4.2 状态和列表

| ID | 场景 | 预期 |
|----|------|------|
| T6 | status | `agent-pipeline status` → 显示最新流水线状态 |
| T7 | list | `agent-pipeline list` → 显示历史列表 |

### 4.3 边界条件

| ID | 场景 | 预期 |
|----|------|------|
| T8 | 超长需求（>4096） | 截断为 4096 字符并提示 |
| T9 | 含特殊字符需求 | 文件名正确，运行成功 |
| T10 | 中文需求 | 项目名中文保留，slug 正确 |

---

## 五、环境配置

```bash
# 安装
cd projects/agent-pipeline
pip install -e .

# 设置 API Key
export ANTHROPIC_API_KEY=sk-xxx

# 运行
agent-pipeline run "调研 AI 编码助手市场"

# 查看状态
agent-pipeline status
agent-pipeline list
```

---

## 六、文件清单（供 Tester 参考）

```
src/agent_pipeline/__init__.py       # 包入口
src/agent_pipeline/models.py         # 数据模型（dataclass）
src/agent_pipeline/state.py          # 状态持久化
src/agent_pipeline/knowledge.py      # 预索引门控 RAG
src/agent_pipeline/orchestrator.py   # 流水线编排器
src/agent_pipeline/agents/scout.py   # Scout ReAct Agent
src/agent_pipeline/cli/main.py       # Click CLI
pyproject.toml                       # 项目配置
requirements.txt                     # 依赖清单
.gitignore                           # Git 忽略规则
```

---

## 七、Phase 2 变更详情

### 7.1 架构变更

| 维度 | Phase 1 | Phase 2 |
|------|---------|---------|
| Agent 数量 | 1（Scout） | 5（Scout/Designer/Builder/Tester/Seller） |
| 编排方式 | Python 函数直线流程 | LangGraph StateGraph（7 节点 + 条件边） |
| 失败处理 | 超时重试，直接退出 | Tester→Builder 回退循环（最多 3 次） |
| 输出命名 | `scout/report.md` | `{producer}→{consumer}--{description}.md` |
| 版本 | 0.1.0 | 0.2.0 |
| LLM | DeepSeek (ChatOpenAI) | DeepSeek (ChatOpenAI，全部 5 Agent 统一) |

### 7.2 Phase 2 新增/修改文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/agent_pipeline/agents/designer.py` | 新增 | Designer Agent — 读 Scout 报告，写需求分析 + 架构设计 |
| `src/agent_pipeline/agents/builder.py` | 新增 | Builder Agent — 读设计文档，写代码到 `builder→tester--src/` |
| `src/agent_pipeline/agents/tester.py` | 新增 | Tester Agent — 对照设计检查代码，写测试报告 + 修复指令 |
| `src/agent_pipeline/agents/seller.py` | 新增 | Seller Agent — 读全部产出，写 README |
| `src/agent_pipeline/orchestrator.py` | **重写** | Python 函数 → LangGraph StateGraph（7 节点 + 条件边） |
| `src/agent_pipeline/agents/scout.py` | 修改 | 输出路径改为 `scout→designer--调研报告.md` |
| `src/agent_pipeline/agents/__init__.py` | 修改 | 导出所有 5 个 Agent 创建函数 |
| `src/agent_pipeline/cli/main.py` | 修改 | 五 Agent 看板 + 进度，版本 0.2.0 |
| `src/agent_pipeline/__init__.py` | 修改 | 版本 0.2.0 |
| `pyproject.toml` | 修改 | 版本 0.2.0 |

### 7.3 Phase 2 新增偏差记录

#### 偏差 P2-B01：Agent System Prompt 未从外部模板读取

**Designer 规格**：从 `agents/templates/*.template.md` 读取 System Prompt。

**实现**：System Prompt 直接嵌入在每个 Agent 文件的 `_get_system_prompt()` 函数中。

**原因**：模板文件路径（`../../agents/templates/`）需要运行时计算。Phase 2 MVP 优先确保可靠性，嵌入方式无外部文件依赖。Phase 3 可提取为模板加载模式。

**影响**：修改 System Prompt 需要编辑 Python 文件。

#### 偏差 P2-B02：read_file 工具未做严格路径隔离

**Designer 规格**：工具路径隔离，只能读取 context_dir 内的文件。

**实现**：`read_file` 工具接受任意路径参数，不做前缀校验。`write_report` 和 `write_code` 保持严格路径隔离。

**原因**：Agent 需要读取上游文件（如 Scout 报告），这些在 context_dir 内。本地 CLI 工具场景安全风险可控。

**影响**：低风险。API Key 仅从环境变量读取。

#### 偏差 P2-B03：run_command 工具使用白名单而非沙箱

**Designer 规格**：Builder/Tester 可使用 `run_command` 做编译检查和测试。

**实现**：命令白名单（`allowed_prefixes`），允许 `python -c`、`pip list`、`ls`、`pytest` 等安全命令。

**原因**：完全沙箱在 CLI 工具中实现复杂。白名单提供足够防护。

**影响**：需要新增命令时需扩展白名单。

### 7.4 StateGraph 节点定义

```
START → parse → scout → designer → builder → tester
                                                │
                                      ┌─────────┴─────────┐
                                      ▼                   ▼
                                  builder (回退)      seller → finalize → END
```

**条件路由规则**：
- `tester→builder--修复指令.md` 存在 + `iteration_count < 3` → 回退到 builder
- `tester→builder--修复指令.md` 存在 + `iteration_count >= 3` → 前进到 seller（带 warning）
- 修复指令文件不存在 → 前进到 seller（通过）

### 7.5 文件命名约定

```
output/{slug}/
├── scout→designer--调研报告.md
├── designer→builder--需求分析.md
├── designer→builder--架构设计.md
├── builder→tester--src/          (代码目录)
├── tester→builder--修复指令.md   (失败时存在)
├── tester→seller--测试报告.md
└── seller→user--README.md
```

### 7.6 Tester 测试要点（Phase 2）

#### 正向功能

| ID | 场景 | 输入 | 预期 |
|----|------|------|------|
| P2-T1 | 五 Agent 完整流水线 | `agent-pipeline run "设计一个TODO应用"` | 所有 5 Agent completed |
| P2-T2 | 输出路径命名 | 任何需求 | Scout 报告路径含 `scout→designer--` |
| P2-T3 | Designer 产出 | 需求调研后 | `designer→builder--需求分析.md` + `--架构设计.md` |
| P2-T4 | Builder 产出 | 设计完成后 | `builder→tester--src/` 目录非空 |
| P2-T5 | Tester 产出 | 代码生成后 | `tester→seller--测试报告.md` 存在 |
| P2-T6 | Seller 产出 | 全部通过后 | `seller→user--README.md` 存在 |

#### 回退循环

| ID | 场景 | 操作 | 预期 |
|----|------|------|------|
| P2-T7 | Tester 发现 bug → Builder 修复 | Tester 写 fix-prompt | Builder 重跑，iteration 递增 |
| P2-T8 | 最多 3 次回退 | 模拟连续 3 次失败 | 第 4 次路由到 Seller |
| P2-T9 | 3 次后仍有 bug | 3 次修复后仍失败 | Seller 产出带"已知限制" |

#### 组件导入

| ID | 验证内容 |
|----|---------|
| P2-T10 | `agent_pipeline.agents.create_designer_agent` 可导入 |
| P2-T11 | `agent_pipeline.agents.create_builder_agent` 可导入 |
| P2-T12 | `agent_pipeline.agents.create_tester_agent` 可导入 |
| P2-T13 | `agent_pipeline.agents.create_seller_agent` 可导入 |
| P2-T14 | `agent_pipeline.orchestrator.create_orchestrator` 编译成功 |

---

## 八、Phase 3 变更详情

> Web UI + SSE 实时推送 + pipeline.log + Eclipse 熄灯

### 8.1 新增文件

| 文件 | 说明 |
|------|------|
| `src/agent_pipeline/log_handler.py` | PipelineLogHandler（BaseCallbackHandler），双写 pipeline.log + asyncio.Queue |
| `src/agent_pipeline/web/__init__.py` | Web 包入口 |
| `src/agent_pipeline/web/server.py` | FastAPI 服务（5 端点：/run, /stream/{id}, /shutdown, /api/pipelines, /） |
| `src/agent_pipeline/web/static/index.html` | Web UI 首页（暗色主题 dashboard） |
| `src/agent_pipeline/web/static/app.js` | SSE 消费者前端逻辑 |
| `src/agent_pipeline/web/static/styles.css` | 暗色主题 CSS（JetBrains Mono + dashboard 风格） |

### 8.2 修改文件

| 文件 | 变更 |
|------|------|
| `src/agent_pipeline/orchestrator.py` | 新增全局 `_pipeline_handler` + 7 节点 handler 注入 + `_invoke_agent` 支持 callbacks |
| `src/agent_pipeline/cli/main.py` | 新增 `serve` 命令（`agent-pipeline serve --port 3456`） |
| `pyproject.toml` | 添加 fastapi, uvicorn, sse-starlette 依赖 |

### 8.3 架构说明

```
agent-pipeline serve
    │
    ▼
FastAPI (同进程)
    │
    ├─ POST /run             启动五 Agent 流水线
    ├─ GET  /stream/{id}     SSE 事件推送
    ├─ POST /shutdown        优雅退出（Eclipse）
    ├─ GET  /api/pipelines   历史流水线列表
    ├─ GET  /                静态页面 (index.html)
    └─ GET  /static/*        静态资源
```

事件源：PipelineLogHandler 双写 pipeline.log（持久化）+ asyncio.Queue（SSE 实时推）

### 8.4 Phase 3 偏差记录

#### 偏差 P3-B01：asyncio.Queue 从线程 put_nowait

**设计规格**：使用 `asyncio.Queue` 作为 SSE 事件中转。

**实现**：`PipelineLogHandler._emit()` 从后台线程调用 `queue.put_nowait(event)`。`asyncio.Queue.put_nowait` 在 CPython 中内部使用 deque + Future.wakeup，从工作线程调用是安全的（try/except 保护）。

**影响**：低风险。所有 `_emit` 调用由 try/except 包裹，队列满或事件循环异常时静默忽略。

#### 偏差 P3-B02：pipeline.log 路径延迟绑定

**设计规格**：handler 创建时指定 pipeline.log 路径。

**实现**：handler 在创建时使用临时路径（`output/_logs/{pipeline_id}/pipeline.log`），在 `parse_node` 执行后通过 `handler.set_log_path()` 更新为真实项目输出目录（`output/{project_slug}/pipeline.log`）。

**原因**：parse_node 运行时才确定 project_slug 和 context_dir，handler 在 create 时无法知道最终路径。

#### 偏差 P3-B03：前端使用原生 JavaScript 而非框架

**设计规格**：Web UI 使用 HTML + CSS + JS 三文件结构。

**实现**：使用原生 JavaScript (ES Modules) 实现 SSE 消费、DOM 操作和事件驱动 UI 更新。无 React/Vue 依赖。

**原因**：减少依赖，与 agent-team-dashboard 风格一致。功能轻量，框架带来的复杂度超过收益。

#### 偏差 P3-B04：SSE keepalive 使用 5 秒超时

**设计规格**：SSE 持续推送事件直到 pipeline_end。

**实现**：使用 `asyncio.wait_for(queue.get(), timeout=5.0)` 实现 5 秒心跳。队列无事件时每 5 秒发送 `: keepalive` 注释保持连接。

**原因**：防止代理/负载均衡器断开长时间无数据的 SSE 连接。

#### 偏差 P3-B05：前端从 /api/pipelines 加载历史

**设计规格**：无此端点要求（设计规格中列出但未详述）。

**实现**：新增 `GET /api/pipelines` 端点返回最近 20 条流水线列表（调用 state.list_pipelines）。

**原因**：为后续前端"历史流水线"功能预留。当前版本仅后端可用。

### 8.5 Phase 3 事件协议

```json
{"time":"22:16:01","agent":"scout","event":"agent_start"}
{"time":"22:16:05","agent":"scout","event":"tool_start","tool":"search_web","input":"CLI TODO"}
{"time":"22:16:08","agent":"scout","event":"tool_end","tool":"search_web"}
{"time":"22:18:22","agent":"scout","event":"agent_end","status":"completed","duration_s":141}
{"time":"22:28:27","agent":null,"event":"pipeline_end","status":"completed"}
```

### 8.6 Tester 测试要点（Phase 3）

#### 模块导入与编译

| ID | 验证内容 |
|----|---------|
| P3-T1 | `agent_pipeline.log_handler.PipelineLogHandler` 可导入 |
| P3-T2 | `agent_pipeline.web.server.app` FastAPI 实例创建成功 |
| P3-T3 | `agent-pipeline serve --help` 显示 serve 命令帮助 |

#### Web 服务功能

| ID | 场景 | 预期 |
|----|------|------|
| P3-T4 | GET / 返回 200 | 返回 index.html（text/html） |
| P3-T5 | POST /run 空需求 | 返回 400 `{"error":"需求不能为空"}` |
| P3-T6 | POST /run 有效需求 | 返回 200 `{"pipeline_id":"pl_..."}` |
| P3-T7 | POST /run 并发请求 | 第二次返回 429 "已有流水线在运行" |
| P3-T8 | GET /stream/{id} 不存在 | 返回 404 |
| P3-T9 | GET /api/pipelines | 返回 JSON 数组 |
| P3-T10 | POST /shutdown | 返回 `{"status":"eclipsed"}`，进程退出 |

#### CLI serve 命令

| ID | 场景 | 预期 |
|----|------|------|
| P3-T11 | `agent-pipeline serve --no-open --port 3456` | 服务启动在 localhost:3456 |
| P3-T12 | `agent-pipeline serve --help` | 显示 serve 命令帮助 |

#### pipeline.log

| ID | 场景 | 预期 |
|----|------|------|
| P3-T13 | pipeline 运行后检查日志 | `output/{slug}/pipeline.log` 存在且非空 |
| P3-T14 | 日志格式验证 | 每行是 JSON，包含 time/agent/event 字段 |
| P3-T15 | pipeline_end 事件 | 日志最后一行是 pipeline_end 事件 |

### 8.7 操作日志

```bash
# Phase 3 全流程测试
agent-pipeline serve --no-open --port 3456 &
curl -X POST http://localhost:3456/run \
  -H "Content-Type: application/json" \
  -d '{"requirement":"设计一个 CLI TODO 应用"}'
# → {"pipeline_id":"pl_20260610_143022_abc123"}

# SSE 测试（新终端）
curl -N http://localhost:3456/stream/pl_20260610_143022_abc123
# → data: {"time":"22:16:01","agent":"scout","event":"agent_start"}
# → data: ...

# Eclipse 测试
curl -X POST http://localhost:3456/shutdown
# → {"status":"eclipsed"}（进程退出）
```

---

*Phase 1 完成于 2026-06-10。Phase 2 升级于 2026-06-10。Phase 3 完成于 2026-06-10。Tester 可据此编写测试用例。*
