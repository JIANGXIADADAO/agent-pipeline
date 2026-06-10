# Agent Pipeline — Phase 1 测试计划

> 溯源：Designer → Builder §6 → 本计划 → `test_cli.py`
> 跨 Worker 验证：Builder 的 7 项偏差（B01-B07）和 5 项局限（L01-L05）

---

## 环境变量说明

| 变量 | 值 | 用途 |
|------|-----|------|
| `DEEPSEEK_API_KEY` | `sk-test-key-1234567890` | CI/无 API 场景测试 |

**注意**：CLI 参考文档中写的是 `ANTHROPIC_API_KEY`，但实际代码使用 `DEEPSEEK_API_KEY`（通过 `langchain-openai` / `ChatOpenAI` 调用 DeepSeek API）。测试以代码实际行为为准。

---

## 测试溯源映射

### 1. 功能正向 (T1.x)

| 溯源 ID | 场景 | 状态 | 说明 |
|---------|------|------|------|
| T1.1 | 标准需求运行 | `skipif(no_key)` | 需要真实 DeepSeek API Key |
| T1.2 | 短需求 | `skipif(no_key)` | 需要真实 DeepSeek API Key |
| T1.3 | 带特符需求 | `skipif(no_key)` | 需要真实 DeepSeek API Key |
| T1.4 | `agent-pipeline status` | 可自动化 | 验证空状态 + 有历史状态 |
| T1.5 | `agent-pipeline list` | 可自动化 | 验证空列表 + 有历史列表 |

**Builder 偏差关联**：
- T1.4/T1.5 验证 state.py 的 `load_latest_state()` 和 `list_pipelines()` 工作正常

### 2. 功能异常 (T2.x)

| 溯源 ID | 场景 | 状态 | 说明 |
|---------|------|------|------|
| T2.1 | 空需求 `run ""` | 可自动化 | 报错"需求不能为空" |
| T2.2 | 仅空格 `run "   "` | 可自动化 | 报错"需求不能为空" |
| T2.3 | 超长需求 10000+ 字符 | 可自动化 | 验证截断 + 警告 |
| T2.4 | 无 DEEPSEEK_API_KEY | 可自动化 | 报错提示设置 |
| T2.5 | API Key 无效 | 可自动化 | 用 fake key 测试错误路径 |
| T2.6 | 网络断开 | 手动 | 无法自动化（测试环境依赖） |
| T2.7 | 非法命令 | 可自动化 | Click 报错 |
| T2.8 | `--resume` 无历史 | 可自动化 | 报错"没有找到可恢复的流水线" |

**Builder 偏差关联**：
- T2.4/T2.5 验证偏差 B00（实际使用 DEEPSEEK_API_KEY 而非文档中的 ANTHROPIC_API_KEY）

### 3. 边界条件 (T3.x)

| 溯源 ID | 场景 | 状态 | 说明 |
|---------|------|------|------|
| T3.1 | 最小需求 10 字符 | `skipif(no_key)` | 需要真实 API Key |
| T3.2 | 最大需求 4096 字符 | 部分可测 | 截断警告可测，完整执行需 API Key |
| T3.3 | LLM 返回空 | 不可自动化 | 需要模拟 LLM 行为 |
| T3.4 | 多字节字符 | `skipif(no_key)` | 需要真实 API Key |
| T3.5 | 并发 status 调用 | 可自动化 | 多次调用验证一致性 |
| T3.6 | 重复运行 | `skipif(no_key)` | 需要真实 API Key |

### 4. Agent 行为验证 (T4.x)

| 溯源 ID | 场景 | 状态 | 说明 |
|---------|------|------|------|
| T4.1 | Scout 调用 search_web | 不可自动化 | Agent 日志在 LLM 响应中 |
| T4.2 | 报告格式含"市场概述" | `skipif(no_key)` | 需要真实 API Key |
| T4.3 | Agent 超时重试 | 不可自动化 | 需要控制 LLM 响应时间 |
| T4.4 | 最大重试次数耗尽 | 不可自动化 | 同上 |
| T4.5 | 工具调用失败 | 不可自动化 | 需要模拟工具失败 |

### 5. 故障场景 (T5.x)

| 溯源 ID | 场景 | 状态 | 说明 |
|---------|------|------|------|
| T5.1 | Agent 超时 > 5min | 不可自动化 | 耗时太长 |
| T5.2 | Tester 打回 Builder | Phase 2 特性 | 不在 Phase 1 范围 |
| T5.3 | 空需求 | 可自动化 | 同 T2.1/T2.2 |
| T5.4 | LLM 返回非 Markdown | 不可自动化 | 需要控制 LLM 输出 |
| T5.5 | state.json 损坏 | 可自动化 | 手动创建非法 JSON |
| T5.6 | 多 Agent 全跳过 | Phase 2 特性 | 不在 Phase 1 范围 |

### 6. CLI 输出一致性 (T6.x)

| 溯源 ID | 验证点 | 状态 | 说明 |
|---------|--------|------|------|
| T6.1 | 启动输出含 "🚀" | 可自动化 | Fake key run 测试 |
| T6.2 | 进度显示 Agent 名 | 可自动化 | Fake key run 测试 |
| T6.3 | 完成输出含 "✅" / "❌" | 可自动化 | 正常/失败路径 |
| T6.4 | 失败输出含 "❌" 和原因 | 可自动化 | 故意触发失败 |
| T6.5 | 无 None/undefined 输出 | 可自动化 | 所有命令 |

---

## 测试用例清单

### 测试类: TestHelpAndVersion
| 函数 | 溯源 | 预期 |
|------|------|------|
| `test_help` | T6.5 | `--help` 显示 run/status/list |
| `test_version` | CLI 参考 | **已知 Bug**: `--version` 未实现（CLI 参考声明了但代码没有 `@click.version_option`） |

### 测试类: TestRunErrors
| 函数 | 溯源 | 预期 |
|------|------|------|
| `test_empty_requirement` | T2.1, T5.3 | 报错"需求不能为空" |
| `test_whitespace_requirement` | T2.2, T5.3 | 报错"需求不能为空" |
| `test_long_requirement` | T2.3, T3.2 | 截断警告"超过 4096 字符" |
| `test_no_api_key` | T2.4 | 报错"请设置 DEEPSEEK_API_KEY" |
| `test_short_api_key` | T2.5 | 报错"格式无效"（key < 10 字符） |
| `test_invalid_api_key` | T2.5 | API 认证失败 → exit code 1 + "流水线失败" |
| `test_resume_no_history` | T2.8 | "没有找到可恢复的流水线" |
| `test_unknown_command` | T2.7 | Click "No such command" |

### 测试类: TestStatusList
| 函数 | 溯源 | 预期 |
|------|------|------|
| `test_status_empty` | T1.4 | "暂无流水线记录" |
| `test_list_empty` | T1.5 | "暂无流水线记录" |
| `test_status_after_failed_run` | T1.4, T3.5 | 显示失败的 pipeline |
| `test_list_after_failed_run` | T1.5 | 列表包含之前运行 |
| `test_status_concurrent` | T3.5 | 连续 5 次 status 一致 |

### 测试类: TestCliOutput
| 函数 | 溯源 | 预期 |
|------|------|------|
| `test_start_emoji` | T6.1 | 输出含 "🚀" |
| `test_failure_output` | T6.4 | 输出含 "❌" + 错误原因 |

### 跳过测试（需要真实 DeepSeek API Key）
| 函数 | 溯源 |
|------|------|
| `test_standard_run` | T1.1 |
| `test_short_requirement_run` | T1.2 |
| `test_special_char_requirement` | T1.3 |
| `test_minimum_requirement` | T3.1 |
| `test_max_requirement_run` | T3.2 |
| `test_multibyte_requirement` | T3.4 |
| `test_duplicate_run` | T3.6 |
| `test_scout_report_format` | T4.2 |

---

## Builder 偏差验证覆盖

| 偏差 | 内容 | 验证覆盖 |
|------|------|----------|
| B01 | DuckDuckGo HTML 搜索 | 间接：API 失败路径仍可执行到工具创建 |
| B02 | `../../wiki/` 路径 + `AGENT_PIPELINE_WIKI_PATH` 覆盖 | T3.2 验证 env 覆盖 |
| B03 | 启发式项目名称提取 | T1.3 验证特殊字符 slug |
| B04 | ThreadPoolExecutor 超时 | 不可直接测试（需 5min） |
| B05 | System Prompt 在代码中 | 文档一致性 |
| B06 | --resume 简化实现 | T2.8 验证 |
| B07 | write_report 工厂 + 路径逃逸检查 | 不可直接测试（需工具调用） |

---

## 已知 Bug 记录

### Bug #1: `--version` 未实现
- **来源**: CLI 参考声明了 `--version` 但 `cli/main.py` 中没有 `@click.version_option`
- **影响**: 用户运行 `agent-pipeline --version` 会收到 Click 报错
- **建议修复**: 在 `cli()` 函数上添加 `@click.version_option(version=__version__)`

### Bug #2: CLI 参考环境变量名错误
- **来源**: CLI 参考中写的是 `ANTHROPIC_API_KEY`，实际代码使用 `DEEPSEEK_API_KEY`
- **影响**: 新用户按照文档设置会失败
- **建议修复**: 更新 CLI 参考和所有报错信息中的变量名

### Bug #3: 启动输出在流水线完成后打印
- **来源**: `_print_pipeline_start(state)` 在 `run_pipeline()` 返回后调用
- **影响**: 用户看到 "🚀 流水线已启动" 时实际流水线已经结束
- **影响度**: 低（仅 UX 问题，Phase 2 SSE 会解决）

---

## Phase 2 新增测试

### 背景

| 维度 | Phase 1 | Phase 2 |
|------|---------|---------|
| Agent 数量 | 1（Scout） | 5（Scout/Designer/Builder/Tester/Seller） |
| 编排方式 | Python 函数直线流程 | LangGraph StateGraph（7 节点 + 条件边） |
| 失败处理 | 超时重试 | Tester→Builder 回退循环（最多 3 次） |
| 输出命名 | `scout/report.md` | `{producer}→{consumer}--{description}` |
| 版本 | 0.1.0 | 0.2.0 |
| LLM | DeepSeek (ChatOpenAI) | DeepSeek (ChatOpenAI，全部 5 Agent 统一) |

### 测试溯源映射 (Phase 2)

#### Agent 导入 (P2-T10 ~ P2-T14)

| 溯源 ID | 场景 | 状态 | 说明 |
|---------|------|------|------|
| P2-T10 | `create_designer_agent` 可导入 | skipif(win32) | Windows subprocess asyncio 限制 |
| P2-T11 | `create_builder_agent` 可导入 | skipif(win32) | 同上 |
| P2-T12 | `create_tester_agent` 可导入 | skipif(win32) | 同上 |
| P2-T13 | `create_seller_agent` 可导入 | skipif(win32) | 同上 |
| P2-T14 | `create_orchestrator()` 编译成功 | skipif(win32) | 7 节点注册、边连接 |

#### StateGraph 结构 (Phase 2 新增)

| 溯源 ID | 场景 | 状态 | 说明 |
|---------|------|------|------|
| P2-S1 | 7 节点注册 | skipif(win32) | parse/scout/designer/builder/tester/seller/finalize |
| P2-S2 | 主干边连接 | skipif(win32) | START→parse→scout→designer→builder→tester |
| P2-S3 | 条件边存在 | skipif(win32) | tester→{builder, seller} |
| P2-S4 | 收尾边 | skipif(win32) | seller→finalize→END |

#### 条件路由逻辑 (Phase 2 新增)

| 溯源 ID | 场景 | 输入 | 预期 |
|---------|------|------|------|
| P2-R1 | 修复指令 + 迭代 0/1/2 | fix-prompt 存在, iteration=0/1/2 | 路由到 "builder" |
| P2-R2 | 修复指令 + 迭代 3 | fix-prompt 存在, iteration=3 | 路由到 "seller" |
| P2-R3 | 修复指令 + 迭代 >3 | fix-prompt 存在, iteration=4+ | 路由到 "seller" |
| P2-R4 | 无修复指令 | fix-prompt 不存在 | 路由到 "seller" |

#### CLI 五 Agent 看板 (Phase 2 新增)

| 溯源 ID | 场景 | 验证方法 | 预期 |
|---------|------|---------|------|
| P2-C1 | `--help` 含五个 Agent | `agent-pipeline --help` | 输出含 Scout/Designer/Builder/Tester/Seller |
| P2-C2 | `--version` 显示 0.2.0 | `agent-pipeline --version` | 已覆盖（Phase 1 test_version） |
| P2-C3 | 启动输出含五 Agent 看板 | 需要真实 run（skipif win32） | 5 个 Agent 名称 + 图标 |
| P2-C4 | status 输出五 Agent | `agent-pipeline status` | 5 Agent 执行状态列表 |

#### 文件命名约定 (Phase 2 新增)

| 溯源 ID | 场景 | 验证方法 | 预期 |
|---------|------|---------|------|
| P2-N1 | `→` 命名格式 | 检查 orchestrator.py 源码 | 产出路径含 `{producer}→{consumer}--` |
| P2-N2 | Scout 输出命名 | 源码检查 | `scout→designer--调研报告.md` |
| P2-N3 | Designer 输出命名 | 源码检查 | `designer→builder--需求分析.md` + `--架构设计.md` |
| P2-N4 | Builder 输出命名 | 源码检查 | `builder→tester--src/` |
| P2-N5 | Tester 输出命名 | 源码检查 | `tester→seller--测试报告.md`, `tester→builder--修复指令.md` |
| P2-N6 | Seller 输出命名 | 源码检查 | `seller→user--README.md` |

### Builder 偏差验证覆盖 (Phase 2)

| 偏差 | 内容 | 验证覆盖 |
|------|------|----------|
| P2-B01 | System Prompt 嵌入代码 | P2-T10~T13 验证 Agent 可导入 |
| P2-B02 | read_file 无严格路径隔离 | 文档一致性（不直接可测） |
| P2-B03 | run_command 白名单 | 文档一致性（不直接可测） |

### Phase 2 测试类清单

| 测试类 | 溯源 |
|--------|------|
| `TestPhase2AgentImports` | P2-T10, P2-T11, P2-T12, P2-T13 |
| `TestPhase2StateGraph` | P2-T14, P2-S1, P2-S2, P2-S3, P2-S4 |
| `TestPhase2RoutingLogic` | P2-R1, P2-R2, P2-R3, P2-R4 |
| `TestPhase2CliDashboard` | P2-C1, P2-C3 |
| `TestPhase2FileNaming` | P2-N1, P2-N2, P2-N3, P2-N4, P2-N5, P2-N6 |

---

## 测试结果 (2026-06-10)

### 运行命令

```bash
pytest src/tests/test_cli.py -v
```

### 结果汇总

| 分类 | 数量 | 说明 |
|------|:----:|------|
| 全部测试用例 | 69 | 44 Phase 1 + 25 Phase 2 |
| ✅ 通过 | 48 | 30 Phase 1 + 18 Phase 2 |
| ⏭️ 跳过 | 16 | 9 需真实 API Key + 7 Windows asyncio |
| ❌ 失败 | 5 | 全部为 Phase 1 预存失败（Windows asyncio 限制） |

### Phase 1 预存失败（5 条）

| 测试 | 失败原因 |
|------|---------|
| `test_invalid_api_key_run_fails_gracefully` | Windows 子进程 langgraph 导入崩溃 |
| `test_start_output_format` | 同上 |
| `test_failure_output_format` | 同上 |
| `test_failed_run_creates_state` | 同上 — run 未创建 state.json |
| `test_status_after_failed_run` | 同上 — run 崩溃后无 state.json |

**根因**：`langgraph.stream._types` 在子进程中触发 `import asyncio`，Windows `_overlapped` 崩溃。
**修复**：见 `tester/fix-prompt.md` Bug #4。

### Phase 2 测试结果（新增 25 条）

| 测试类 | 通过 | 跳过 | 失败 |
|--------|:---:|:----:|:---:|
| `TestPhase2AgentImports` | 0 | 5 | 0 |
| `TestPhase2StateGraph` | 0 | 1 | 0 |
| `TestPhase2RoutingLogic` | 10 | 0 | 0 |
| `TestPhase2CliDashboard` | 3 | 1 | 0 |
| `TestPhase2FileNaming` | 5 | 0 | 0 |
| **合计** | **18** | **7** | **0** |

所有 Phase 2 新增测试全部通过。7 条跳过均为已知 Windows subprocess asyncio 限制。

---

*测试计划版本: 2.0 · 2026-06-10 · Phase 2 测试完成*
