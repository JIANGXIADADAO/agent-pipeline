---
title: "Agent Pipeline — 架构设计"
type: overview
tags: [agent-pipeline, architecture, react-agent, langgraph-upgrade-path]
created: 2026-06-10
updated: 2026-06-10
---

# Agent Pipeline — 架构设计

> **Phase 1**：Python 函数 Orchestrator + `create_react_agent`。不提前引入外层 LangGraph。
> **Phase 2+**：Orchestrator 升级为 LangGraph StateGraph（当需要非线性控制流时）。
> 预索引门控 RAG 是差异化亮点。

---

## 一、全局架构图（Phase 1）

```
                                                          
  CLI: agent-pipeline run "调研 AI 编码助手市场"
       │
       ▼
╔══════════════════════════════════════════════════════════╗
║     Orchestrator（Python 函数，~30 行，无 LangGraph）      ║
║                                                          ║
║  1. parse_requirement(需求) → project_name, slug         ║
║  2. match_index(需求, wiki/index.md) → 知识上下文          ║
║  3. create_scout_agent() → System Prompt + 工具          ║
║  4. agent.invoke({messages: [...]}) → ReAct 循环         ║
║  5. 写入 state.json → 输出结果                            ║
║                                                          ║
║  Phase 1 是直线——无分支、无条件路由、无回退。              ║
║  Phase 2+ 升级为 LangGraph StateGraph。                  ║
╚══════════════════════════════════╤═══════════════════════╝
                                   │ 调用
                                   ▼
╔══════════════════════════════════════════════════════════╗
║       Scout ReAct Agent (create_react_agent)             ║
║                                                          ║
║  System Prompt: agents/templates/scout.template.md       ║
║  Tools: search_web, read_url, write_report,              ║
║         query_knowledge                                  ║
║  ReAct 循环: Think → Tool Call → Observe → ... → Final  ║
╚══════════════════════════════════╤═══════════════════════╝
                                   │
                                   ▼
╔══════════════════════════════════════════════════════════╗
║     预索引门控 RAG（Phase 1：子串匹配 index.md）           ║
║                                                          ║
║  需求 → index.md 关键词匹配                               ║
║    ├─ 命中 → 加载对应 wiki 页面                            ║
║    └─ 未命中 → "knowledge_source: none"                  ║
║                                                          ║
║  Phase 3+ 引入 pgvector 语义搜索。                        ║
╚══════════════════════════════════════════════════════════╝
```

### Phase 2+ 升级路径

```
Phase 1:                                Phase 2+:
                                        
  Python 函数                            LangGraph StateGraph
                                        
  run_pipeline()                        parse → scout → designer
    1. parse                               │        │
    2. match_index                         │        ▼
    3. agent.invoke()                      │     builder
    4. save_state                          │        │
                                           │        ▼
                                           │     tester
                                           │        │
                                           │   ┌────┴─────┐
                                           │   ▼          ▼
                                           │ pass        fail→back to builder
                                           │   │
                                           │   ▼
                                           │ seller → finalize
```

Phase 1 的函数直接变成 StateGraph 的一个线性子图。Agent 节点实现不变。升级只是在外面包一层路由。

---

## 二、技术栈选型

| 组件 | Phase 1 选型 | Phase 2+ 变化 | 理由 |
|------|:-----------:|:-------------:|------|
| **编排层** | Python 函数 | → LangGraph StateGraph | Phase 1 是直线流程，不需要状态机。Phase 2+ Tester→Builder 回退需要条件路由 |
| **Agent 内层** | `create_react_agent` | 不变 | Phase 1 到 Phase 5 始终是 Agent 实现方式 |
| **LLM** | Anthropic SDK (Claude) | 不变 | 项目既定。Tool use 稳定性 + 200K 上下文 |
| **CLI** | Click ≥8.1 | 不变 | Python 标准 CLI 库 |
| **状态持久化** | JSON 文件 (`state.json`) | → PostgreSQL (Phase 3) | Phase 1 零数据库依赖 |
| **向量数据库** | 无（仅 index.md 子串匹配） | → pgvector | Phase 1 不引入向量检索。需要时再加 |
| **Web UI** | 无 | → Next.js (复用 agent-team-dashboard) | Phase 2 引入 |
| **HTTP / SSE** | 无 | → FastAPI + sse-starlette | Phase 2 引入 |

### Phase 1 依赖清单

```
anthropic>=0.40.0
langgraph>=0.2.0          # 仅用 create_react_agent，不用 StateGraph
langchain-anthropic>=0.2.0
click>=8.1.0
httpx>=0.27.0             # search_web + read_url 工具用
beautifulsoup4>=4.12.0    # HTML 解析
```

**Phase 1 不需要安装**：pgvector, fastapi, sse-starlette, next.js, postgresql。

---

## 三、数据模型

### 3.1 PipelineState（Python dataclass，非 LangGraph TypedDict）

```python
from dataclasses import dataclass, field
from typing import Optional, Literal

@dataclass
class AgentOutput:
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_path: Optional[str] = None
    summary: str = ""
    raw_output: str = ""
    error: Optional[str] = None
    retry_count: int = 0
    artifacts: list[str] = field(default_factory=list)

@dataclass
class PipelineState:
    requirement: str
    project_name: str = ""
    project_slug: str = ""
    current_agent: str = "scout"
    phase: str = "scout"
    agent_outputs: dict[str, AgentOutput] = field(default_factory=dict)
    status: str = "idle"           # idle | running | completed | failed
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context_dir: str = ""
    knowledge_hit: bool = False
    knowledge_sources: list[str] = field(default_factory=list)
    pipeline_id: str = ""
    created_at: str = ""
    updated_at: str = ""
```

### 3.2 状态持久化格式 (state.json)

```json
{
  "pipeline_id": "pl_20260610_001",
  "status": "completed",
  "requirement": "调研 AI 编码助手市场",
  "project_name": "ai-coding-assistant-market-research",
  "phase": "scout",
  "agent_outputs": {
    "scout": {
      "status": "completed",
      "output_path": "output/scout/report.md",
      "summary": "市场调研报告已生成",
      "started_at": "2026-06-10T10:00:00Z",
      "completed_at": "2026-06-10T10:02:15Z"
    }
  },
  "errors": [],
  "warnings": []
}
```

---

## 四、Phase 1 伪代码

```python
# src/lib/orchestrator.py (Phase 1: ~30 行)

def run_pipeline(requirement: str) -> PipelineState:
    state = PipelineState(requirement=requirement)
    state.pipeline_id = generate_pipeline_id()
    state.context_dir = f"output/{state.project_name}"

    # Step 1: 解析需求
    state = parse_requirement(state)

    # Step 2: 预索引门控 RAG（index.md 匹配）
    state = match_index_knowledge(state, index_path="wiki/index.md")

    # Step 3: 创建并运行 Scout Agent
    agent = create_scout_agent()
    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": build_scout_prompt(state)
        }]
    })

    # Step 4: 检查结果并保存状态
    state = save_scout_result(state, result)
    save_state(state)  # → state.json

    # Step 5: 输出到 CLI
    print_result(state)
    return state
```

---

## 五、Agent 工具权限表（全五 Agent，Phase 2+ 启用）

| 工具 | Scout | Designer | Builder | Tester | Seller | 用途 |
|------|:-----:|:--------:|:-------:|:------:|:------:|------|
| **search_web** | P1 | | | | | 搜索市场/技术信息 |
| **read_url** | P1 | | | | | 读网页内容 |
| **write_report** | P1 | P2 | | | | 写调研/报告 |
| **read_file** | | P2 | P2 | P2 | P2 | 读上游产出 |
| **query_docs** | | P2 | | | | 查技术文档 |
| **write_code** | | | P2 | | | 生成代码 |
| **run_lint** | | | P2 | | | 编译检查 |
| **run_tests** | | | | P2 | | 执行测试 |
| **write_fix_prompt** | | | | P2 | | 修复指令 |
| **read_all_outputs** | | | | | P2 | 读全部产出 |
| **write_readme** | | | | | P2 | 写用户文档 |
| **gen_changelog** | | | | | P2 | 调用 changelog-tool |
| **create_pr** | | | | | P2 | 创建 GitHub PR |
| **query_knowledge** | P1 | P2 | P2 | P2 | P2 | 预索引 RAG 查询 |

P1 = Phase 1 实现，P2 = Phase 2 实现。

---

## 六、预索引门控 RAG 设计

```
用户需求
    │
    ▼
┌─────────────────────────────┐
│  Step 1: 索引匹配 (Phase 1)  │
│  需求 → 提取关键词            │
│  → 匹配 index.md 条目        │
│  → 命中: 加载 wiki 页面      │
│  → 未命中: knowledge=none   │
└─────────────────────────────┘
    │ (Phase 3+ 未命中时)
    ▼
┌─────────────────────────────┐
│  Step 2: 向量检索 (Phase 3)  │
│  需求 → Embedding            │
│  → pgvector 余弦搜索 Top-5   │
│  → 作为 Agent 上下文         │
└─────────────────────────────┘
```

Phase 1 不做向量检索。预索引匹配是简单子串匹配。Phase 3 才引入 pgvector。

---

## 七、错误处理

| 场景 | Phase 1 处理 | Phase 2+ 增强 |
|------|:-----------:|:------------:|
| LLM API 调用失败 | 指数退避重试 2 次（1s→4s） | LangGraph 节点级重试 |
| Agent 超时（>5min） | 重试 1 次 | 条件路由跳过或终止 |
| 状态文件写入失败 | 提示用户，输出到 stdout | 自动重试 |
| 无 API Key | 立即报错退出 | 同 |
| 空需求 | 立即报错退出 | 同 |

---

## 八、安全边界

| 维度 | Phase 1 |
|------|---------|
| API Key | 仅从 `ANTHROPIC_API_KEY` 环境变量读取，不写入文件 |
| 文件写入 | Agent 的 write_report 工具只允许在 `context_dir/` 内写入 |
| 网络访问 | search_web + read_url 只出不进（只读不写外部） |
| 代码执行 | Phase 1 无代码执行（Scout 只搜索+读网页+写报告） |
| .gitignore | 忽略 `output/`, `state.json`, `.env` |

---

## 九、上下文目录结构

```
{context_dir}/
├── requirement.txt           # 用户原始需求
├── project.json              # 解析后的项目元数据
├── state.json                # 流水线状态（断点恢复用）
└── scout/
    ├── report.md             # 调研报告
    └── sources.json          # 调研来源
```
