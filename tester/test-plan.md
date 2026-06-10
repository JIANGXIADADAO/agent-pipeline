# Agent Pipeline — 测试计划

> 溯源：Designer → Builder §6 → 本计划 → `test_cli.py`
> 跨 Worker 验证：Builder 的偏差记录和 CLI 参考

---

## 环境变量说明

| 变量 | 值 | 用途 |
|------|-----|------|
| `DEEPSEEK_API_KEY` | `sk-test-key-1234567890` | CI/无 API 场景测试 |

**注意**：CLI 参考文档中写的是 `ANTHROPIC_API_KEY`，但实际代码使用 `DEEPSEEK_API_KEY`（通过 `langchain-openapi` / `ChatOpenAI` 调用 DeepSeek API）。测试以代码实际行为为准。

---

## Phase 1 & 2 测试（已归档）

Phase 1 和 Phase 2 测试已全部在 `test_cli.py` 中实现并通过。

| 分类 | 数量 | 说明 |
|------|:----:|------|
| 全部测试用例 | 69 | 44 Phase 1 + 25 Phase 2 |
| Phase 2 通过 | 18 | 全部 Phase 2 新增 |
| Phase 2 跳过 | 7 | Windows subprocess asyncio 限制 |

详情见下方 Phase 2 各章节。

---

## Phase 3 — 测试溯源映射

### 模块导入（P3-T1 ~ P3-T3）

| 溯源 ID | 验证内容 | 方法 | 预期 |
|---------|---------|------|------|
| P3-T1 | `agent_pipeline.log_handler.PipelineLogHandler` 可导入 | subprocess import | import 成功 |
| P3-T2 | `agent_pipeline.web.server.app` FastAPI 实例 | subprocess import | app 创建成功 |
| P3-T3 | `agent-pipeline serve --help` 显示 serve 命令 | CLI subprocess | 输出含 serve 命令信息 |

### Web 服务功能（P3-T4 ~ P3-T10）

| 溯源 ID | 场景 | 方法 | 预期 |
|---------|------|------|------|
| P3-T4 | GET / 返回 200 | TestClient | 200 + text/html |
| P3-T5 | POST /run 空需求 | TestClient | 400 `{"error":"..."}` |
| P3-T6 | POST /run 有效需求 | TestClient | 200 `{"pipeline_id":"pl_..."}` |
| P3-T7 | POST /run 并发请求 | TestClient | 429 "已有流水线在运行" |
| P3-T8 | GET /stream/{id} 不存在 | TestClient | 404 |
| P3-T9 | GET /api/pipelines | TestClient | JSON 数组 |
| P3-T10 | POST /shutdown | TestClient + 源码 | 返回 `{"status":"eclipsed"}` |

### CLI serve 命令（P3-T11 ~ P3-T12）

| 溯源 ID | 场景 | 方法 | 预期 |
|---------|------|------|------|
| P3-T11 | `agent-pipeline serve --no-open --port 3456` | 源码验证 | argparse 解析正确 |
| P3-T12 | `agent-pipeline serve --help` | CLI subprocess | 显示 serve 帮助信息 |

### pipeline.log（P3-T13 ~ P3-T15 + handler 单元测试）

| 溯源 ID | 场景 | 方法 | 预期 |
|---------|------|------|------|
| P3-T13 | pipeline 运行后检查日志 | handler 单元测试 | emit 写文件成功 |
| P3-T14 | 日志格式验证 | handler 单元测试 | 每行 JSON 含 time/agent/event |
| P3-T15 | pipeline_end 事件 | handler 单元测试 | emit pipeline_end 事件 |

**额外 handler 测试**：

| 场景 | 方法 | 预期 |
|------|------|------|
| QueueFull 不抛异常 | 单元测试 asyncio.Queue maxsize=1 | 静默忽略 |
| emit 异常不阻断 | 单元测试 mock 写失败 | 不抛出异常 |
| CLI 模式 event_queue=None | 单元测试 | emit 只写文件，不推 SSE |
| `now_iso()` 格式 | 单元测试 | 返回 HH:MM:SS 格式 |
| 前端文件存在 | os.path.exists | index.html / app.js / styles.css 存在 |

---

## 前端文件验证

| 文件 | 路径 | 应存在 |
|------|------|:------:|
| index.html | `src/agent_pipeline/web/static/index.html` | 是 |
| app.js | `src/agent_pipeline/web/static/app.js` | 是 |
| styles.css | `src/agent_pipeline/web/static/styles.css` | 是 |

---

## 测试类清单（Phase 3）

| 测试类 | 溯源 ID |
|--------|---------|
| `TestPhase3ModuleImport` | P3-T1, P3-T2 |
| `TestPhase3ServeHelp` | P3-T3, P3-T12 |
| `TestPhase3FrontendFiles` | 前端文件存在性 |
| `TestPhase3LogHandler` | P3-T13, P3-T14, P3-T15 + QueueFull/异常 |
| `TestPhase3WebServer` | P3-T4 ~ P3-T9 |
| `TestPhase3Shutdown` | P3-T10 |

---

## Builder 偏差验证覆盖（Phase 3）

| 偏差 | 内容 | 验证覆盖 |
|------|------|----------|
| P3-B01 | asyncio.Queue 从线程 put_nowait | handler _emit 单元测试验证 QueueFull 安全 |
| P3-B02 | pipeline.log 路径延迟绑定 | handler set_log_path 方法测试 |
| P3-B03 | 前端使用原生 JS | 静态文件存在性检查 |
| P3-B04 | SSE keepalive 5 秒超时 | 源码验证（server.py EventSourceResponse） |
| P3-B05 | /api/pipelines 历史查询 | P3-T9 TestClient 端点测试 |

---

## Phase 3 测试结果

### 运行命令

```bash
cd projects/agent-pipeline
pytest src/tests/test_cli.py -v
```

### 结果汇总

（待运行后填写）

---

*测试计划版本: 3.0 · 2026-06-10 · Phase 3 测试规划*
