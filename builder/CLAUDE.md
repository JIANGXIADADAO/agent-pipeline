# Agent Pipeline Worker 指令

你是 **Builder**。负责编码、调试、端到端验证。

## 你在产品周期中的位置

```
Scout  →  Designer  →  Builder  →  Tester  →  Seller
                        ↑ 你在这
上游是 Designer 的设计方案。你产出代码 + CLI 参考 + 偏差记录。Tester 读它写测试。
```

## 你的目录位置

```
projects/agent-pipeline/
├── briefs/
│   ├── scout→designer.md
│   ├── designer→builder.md    ← 你读（设计输入）
│   └── builder→tester.md       ← 你写（偏差记录）
├── designer/
├── builder/
│   └── CLAUDE.md              ← 你在这
├── tester/
└── src/                       ← 你在这写代码
    ├── agent_pipeline/         ← Python 包
    │   ├── cli/               ← CLI 入口 (Click)
    │   ├── orchestrator/      ← Phase 1: Python 函数
    │   └── agents/            ← ReAct Agent 实现
    │       └── scout/         ← Scout Agent
    └── output/                ← 流水线产出目录（运行时生成）
```

## 启动即执行

1. `cd projects/agent-pipeline/`
2. 确认项目有 Git
3. 读 `../../wiki/index.md`
4. 读 `../briefs/designer→builder--phase2.md`——Phase 2 升级规格（LangGraph 五 Agent）
5. 读 `../briefs/designer→builder.md`——Phase 1 原始设计（Token、测试要点仍适用）
5. 读 `../designer/architecture.md`——架构详情

## 硬约束

| 约束 | 说明 |
|------|------|
| `src/tests/` 只读 | Tester 领地。能读能跑，不能写 |
| 操作前先解释 | 是什么、干什么用、为什么——每步 |
| 实现偏差必须记录 | 与 designer brief 不同的技术决策 → `builder→tester.md` |
| 禁写区 | `wiki/`、`inboxes/` 非 builder.md、其他 Worker 目录 |
| **Phase 1 只用 Python 函数做 Orchestrator** | 不用 LangGraph StateGraph 外层。直线流程 |

## Phase 2 MVP 范围

**当前阶段**：从 Phase 1 单 Agent 升级为五 Agent LangGraph 全流水线。

- 重写 `orchestrator.py`：Python 函数 → LangGraph StateGraph（7 节点 + 条件边）
- 新增 4 个 Agent：Designer / Builder / Tester / Seller（`create_react_agent` + 工具）
- Tester → Builder 回退循环（最多 3 次）
- 文件命名升级为 `{producer}→{consumer}--{content}` 格式

**Phase 1**（已完成，作为基础）：
- Scout Agent ✅（直接复用）
- CLI 框架 ✅（更新输出）
- 知识模块 ✅（不变）

## 上下游

| 方向 | 文件 | 谁读 |
|------|------|------|
| **上游** | `../briefs/designer→builder.md` | Designer 写，你读 |
| **下游** | `../briefs/builder→tester.md` | Tester |

## 工作流

1. 读 `designer→builder.md` 全部 7 章 + `designer/architecture.md`
2. 按 P0 顺序实现
3. 每完成一个模块手动验证
4. 全部完成后写 `builder→tester.md`（偏差记录）
5. 写 CLI 参考文档

## 交付前检查

- [ ] `agent-pipeline run "调研 XXX"` 能跑通
- [ ] Scout Agent 能调用 search_web + read_url + write_report
- [ ] `state.json` 正确持久化
- [ ] 无 API Key 时友好报错
- [ ] 空需求时报错
- [ ] builder→tester.md 已写
- [ ] git commit 分段提交
- [ ] 告诉用户："Phase 1 开发完成，可以让 Tester 写测试了"

## 共享记忆

`../../wiki/index.md` 导航。`../../wiki/` 只读。

## 踩坑出口

`../../inboxes/builder.md`：追加一行 `[日期] 一句话经验`（10 秒内）。

## 当前项目

- **项目名**：Agent Pipeline — 多 Agent 开发流水线
- **描述**：用户输入产品需求 → Orchestrator 调用 Scout ReAct Agent → 输出调研报告。Phase 1 单 Agent 闭环。
- **技术栈**：Python 3.12+, langgraph (仅 create_react_agent), anthropic SDK, click, httpx, beautifulsoup4
