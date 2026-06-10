# Agent Pipeline — Scout → Designer 交接

## 项目定位

做一个**多 Agent 开发流水线**——用户输入产品需求，五个 Agent 自动协作，输出可运行代码 + 测试 + CHANGELOG。

核心差异化：
1. **预索引门控 RAG**——Orchestrator 先读 index.md 定位知识域，命中走内部知识，未命中才走向量检索。不是纯 RAG。
2. **五 Agent 分工模型已手动验证**——Cub 在三个项目（changelog-tool / agent-team-dashboard / Company-OS）上手动协调过完全相同的五阶段分工，证明了模型可行。
3. **复用已有资产**——agent-team-dashboard 的 Web UI 直接接入，changelog-tool 的生成逻辑直接复用，Company-OS 的 Worker 模板提取为 System Prompt。

## 市场背景

2026 年 AI Agent 岗位 JD 统一要求三根柱子：
- **Agent 编排**：LangGraph 多 Agent 协作、工具使用、状态管理（100% JD）
- **知识/检索**：RAG 管道、向量数据库、预索引（100% JD）
- **评估与安全**：护栏、LLM-as-judge、回归测试（几乎所有大厂 JD）

现有三个项目合计仅覆盖约 0.5 根柱子。本项目的目标是三根全中。

## 关键设计约束

1. **基础 LLM 用 Claude API**（你已经熟悉的 Anthropic SDK）
2. **编排框架用 LangGraph**（2026 跨公司共同语言，Python）
3. **Web UI 复用 agent-team-dashboard**（已有 SSE 推送 + Pipeline 可视化）
4. **CHANGELOG 生成复用 changelog-tool**
5. **五个 Agent 的 System Prompt 从 agents/templates/ 提取**
6. **Phase 1 目标**：Orchestrator + Scout Agent 单 Agent 闭环，命令行可跑
7. **最终交付物**：开源 GitHub 仓库，含完整 live demo

## 参考架构讨论

Cub + 用户的对话中已经确定了以下关键设计决策：

### 分阶段架构

**Phase 1**（单 Agent 闭环，当前交付）：
- **Orchestrator**：简单 Python 函数——不需要 LangGraph。流程是直线：解析需求 → 调 Agent → 输出。没有分支、没有条件路由。约 30 行代码。
- **Agent**：每个 Agent 是 ReAct 工具调用循环（`langgraph.prebuilt.create_react_agent`），有自己的 System Prompt + 角色级工具集

**Phase 2+**（多 Agent 全流水线）：
- **Orchestrator 升级为 LangGraph StateGraph**——当需要非线性控制流时引入：Tester 打回 Builder、Agent 超时跳过、条件分支
- 升级路径直接：Phase 1 的 Python 函数改为 StateGraph 节点，5 个 Agent 各占一个节点
- **Agent 内层不变**——`create_react_agent` 从 Phase 1 到 Phase 5 始终是 Agent 的实现方式

**设计原则**：不提前引入框架。当前阶段不需要 LangGraph → 不用。需要时再升级。

### Agent 工具权限按角色裁剪
| Agent | 可用工具 |
|-------|----------|
| Scout | 搜索 + 读网页 + 写报告 |
| Designer | 读文件 + 查技术文档 + 写设计文档 |
| Builder | 读设计 + 写代码 + 跑编译检查 |
| Tester | 读代码 + 跑测试 + 写 fix-prompt |
| Seller | 读全部产出 + 写 README/CHANGELOG + 创建 PR |

### 预索引门控 RAG
- Orchestrator 启动时读 index.md（手动策展的项目索引）
- 命中 → 直接加载对应 wiki 页面，不触发向量检索
- 未命中 → 走 RAG（pgvector + embeddings）
- 这是差异化亮点——"什么时候不该用 RAG"

### 渐进式 MVP
- Phase 1：Orchestrator + 单 Agent（Scout），命令行能跑
- Phase 2：补全五 Agent 全流水线
- Phase 3：接 agent-team-dashboard Web UI
- Phase 4：RAG 知识库 + 评估系统（LLM-as-judge + 护栏）
- Phase 5：输出层（PR + CHANGELOG + 部署）

## 竞品参照

| 竞品 | 我们的差异 |
|------|-----------|
| GPT Pilot / Devin | 封闭、昂贵、黑盒。我们：开源、可视化工作流、明确分工 Agent |
| CrewAI | 纯 Agent 协作，无预索引概念。我们：预索引门控 RAG |
| LangGraph 官方示例 | Demo 级，不做完整产品。我们：端到端生产化流水线 |
| MetaGPT | 学术项目，未维护。我们：面向真实使用和招聘展示 |

## 用户画像

- **主用户**：招聘方/面试官——打开浏览器 → 输入需求 → 看到五个 Agent 自动协作 → 拿到可运行代码
- **次用户**：JIANGXIA 自己——用这个系统加速后续产品开发
- **三次用户**：开源社区开发者——clone 之后自己部署自己的 Agent 流水线
