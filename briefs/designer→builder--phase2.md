# Agent Pipeline — Designer → Builder Phase 2

> Phase 2：从单 Agent Python 函数升级为五 Agent LangGraph StateGraph

## Phase 2 范围

**In Scope：**
- orchestrator.py 重写：Python 函数 → LangGraph StateGraph（7 节点 + 条件边）
- 4 个新 Agent：Designer / Builder / Tester / Seller（每个都是 create_react_agent + 工具）
- Tester → Builder 回退循环（最多 3 次）
- 文件命名约定升级：`{producer}→{consumer}--{content}` 格式
- CLI 输出更新：显示五 Agent 进度而非仅 Scout

**Out of Scope（Phase 3+）：**
- Web UI / SSE
- pgvector 向量检索
- LLM-as-judge 评估框架

## 技术要点

1. **外层 LangGraph StateGraph** — 7 个 node（parse/scout/designer/builder/tester/seller/finalize）+ 条件边
2. **内层不变** — `create_react_agent`，从 Phase 1 的 1 个变 5 个
3. **Scout Agent 直接复用** — Phase 1 的代码基本不动，作为 StateGraph 的一个节点
4. **所有 Agent 用 DeepSeek** — `ChatOpenAI(base_url="https://api.deepseek.com")`
5. **文件命名** — `{producer}→{consumer}--{description}` (详见 phase2-plan.md 3.2 节)

## 参考文档（必读）

- `../designer/architecture.md` — 全局架构图、数据模型、状态流转
- `../designer/phase2-plan.md` — 五 Agent 完整定义、回退机制、数据协议
- `../../agents/templates/designer.template.md` — Designer System Prompt 来源
- `../../agents/templates/builder.template.md` — Builder System Prompt 来源
- `../../agents/templates/tester.template.md` — Tester System Prompt 来源
- `../../agents/templates/seller.template.md` — Seller System Prompt 来源
- `../briefs/designer→builder.md` — Phase 1 的原始设计（技术栈、Token、测试要点仍适用）

## Phase 2 Agent 工具权限表

| Agent | 工具 | 来源 |
|-------|------|------|
| Scout | search_web, read_url, write_report, query_knowledge | 复用 Phase 1 |
| Designer | read_file, write_report, query_knowledge | 新增 |
| Builder | read_file, write_code, run_command, query_knowledge | 新增 |
| Tester | read_file, run_command, write_report | 新增 |
| Seller | read_file, write_report, query_knowledge | 新增 |

## 期望产出

1. `src/agent_pipeline/orchestrator.py` — 重写为 LangGraph StateGraph
2. `src/agent_pipeline/agents/scout.py` — 微调输出路径
3. `src/agent_pipeline/agents/designer.py` — 新增
4. `src/agent_pipeline/agents/builder.py` — 新增
5. `src/agent_pipeline/agents/tester.py` — 新增
6. `src/agent_pipeline/agents/seller.py` — 新增
7. `src/agent_pipeline/cli/main.py` — 更新进度输出
8. `builder→tester.md` — 偏差记录

## 编码顺序

1. 先写 StateGraph 骨架（7 节点 + 边），每个节点先 return 占位
2. 逐个实现 Agent 节点（先 Designer → Builder → Tester，最后 Seller）
3. 实现 Tester→Builder 条件路由
4. 更新 CLI
5. 手动验证五 Agent 完整流水线
