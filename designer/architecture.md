---
title: "Agent Pipeline — 架构设计"
type: overview
tags: [agent-pipeline, architecture, state-graph, react-agent, langgraph]
created: 2026-06-10
updated: 2026-06-10
---

# Agent Pipeline — 架构设计

> 双层架构：外层 LangGraph StateGraph（Agent 编排）+ 内层 `create_react_agent`（工具调用循环）。
> 预索引门控 RAG 是差异化亮点。

---

## 一、全局架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent Pipeline CLI / Web UI              │
│  agent-pipeline run "需求"                                   │
│  agent-pipeline run --resume                                │
└──────────────────────────┬──────────────────────────────────┘
                           │ 需求文本
                           ▼
┌────────────────────────────────────────────────────────────┐
│              外层 Orchestrator (LangGraph StateGraph)         │
│                                                              │
│  ┌─────────┐  ┌──────────┐  ┌────────┐  ┌──────┐  ┌──────┐ │
│  │ Parse   │→ │ Route    │→ │ Exec   │→ │Cond  │→ │Final │ │
│  │Require │  │ Agent    │  │ Agent  │  │Check │  │Output│ │
│  └─────────┘  └──────────┘  └────────┘  └──────┘  └──────┘ │
│       │            │            │         │                  │
│       ▼            ▼            ▼         ▼                  │
│  Shared State (PipelineState) ←─────────────                │
│  - requirement, current_agent                                │
│  - agent_outputs: {scout, designer, ...}                     │
│  - status, errors, retry_count                              │
└──────────────────────────┬──────────────────────────────────┘
                           │ 分派
                           ▼
┌────────────────────────────────────────────────────────────┐
│         内层 ReAct Agent (create_react_agent)               │
│                                                              │
│  ┌──────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐ │
│  │Scout │  │Designer│  │Builder │  │Tester  │  │Seller  │ │
│  │Agent │  │Agent   │  │Agent   │  │Agent   │  │Agent   │ │
│  └──┬───┘  └───┬────┘  └───┬────┘  └───┬────┘  └───┬────┘ │
│     │          │            │            │           │       │
│     ▼          ▼            ▼            ▼           ▼       │
│  Tools:    Tools:       Tools:       Tools:      Tools:    │
│  ──────    ──────       ──────       ──────      ──────    │
│  search    read_file    read_design  read_code   read_all  │
│  read_url  query_docs   write_code   run_tests   write_read│
│  write_rep  write_doc   compile_chk  write_fix   changelog │
│  ort       ument        eck         prompt      create_pr │
└────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────┐
│              预索引门控 RAG 系统                               │
│                                                              │
│  用户需求 → index.md 命中？                                    │
│    ├─ 是 → 直接加载 wiki 页面（不触发向量检索）                  │
│    └─ 否 → pgvector 语义搜索 → 返回 Top-K 片段                │
│                                                              │
│  亮点："什么时候不该用 RAG" — 内部策展知识优先                    │
└────────────────────────────────────────────────────────────┘
```

---

## 二、技术栈选型

| 组件 | 选型 | 版本 | 理由 |
|------|------|------|------|
| **编排层** | LangGraph (Python) | ≥0.2.0 | 跨公司共同语言（100% JD 提及）。StateGraph 原生支持多 Agent 路由、条件边、状态持久化 |
| **Agent 内层** | `langgraph.prebuilt.create_react_agent` | ≥0.2.0 | 官方支持的 ReAct 模式，内置 ToolNode + 消息循环，减少自维护 Bug |
| **LLM** | Anthropic SDK (Claude) | ≥0.40.0 | 项目既定决策。Claude 的 tool use 稳定性、长上下文窗口（200K）适合多 Agent 场景 |
| **向量数据库** | pgvector (PostgreSQL) | ≥0.7.0 | 开源、SQL 原生、Supabase 生产兼容。相比 Pinecone 无厂商锁定 |
| **Embeddings** | `voyage-2` 或 `text-embedding-3-small` | — | 配合 pgvector 的常用嵌入模型，LangChain 原生集成 |
| **Web UI** | Next.js (复用 agent-team-dashboard) | ≥14 | 已有 SSE 推送 + Pipeline 可视化组件，直接接入减少开发量 |
| **SSE 传输** | Server-Sent Events | — | agent-team-dashboard 已有实现，单向推送适合流水线状态更新 |
| **状态持久化** | JSON 文件 (Phase 1) → PostgreSQL (Phase 3+) | — | Phase 1 避免数据库依赖，JSON 足够；Phase 3 统一为 PostgreSQL |
| **CLI 框架** | Click (Python) | ≥8.1 | Python 生态标准 CLI 库，argparse 替代也可接受 |
| **运行时** | Python 3.12+ | ≥3.12 | 类型提示增强、性能改进。LangGraph 官方推荐 |

---

## 三、数据模型

### 3.1 PipelineState（StateGraph 共享状态）

```python
from typing import TypedDict, Optional, Literal
from langgraph.graph import MessagesState

class AgentOutput(TypedDict):
    """单个 Agent 的输出"""
    status: Literal["pending", "running", "completed", "failed"]
    started_at: Optional[str]           # ISO 8601
    completed_at: Optional[str]         # ISO 8601
    output_path: Optional[str]          # 产出文件路径
    summary: str                        # 一句话摘要
    raw_output: str                     # Agent 完整输出
    error: Optional[str]                # 失败时错误信息
    retry_count: int                    # 当前重试次数
    artifacts: list[str]                # 产出物文件列表

class PipelineState(TypedDict):
    """完整的流水线状态"""
    # 输入
    requirement: str                    # 用户输入的需求
    project_name: str                   # AI 提取的项目名称
    project_slug: str                   # AI 生成的目录名
    
    # 路由
    current_agent: str                  # 当前运行的 Agent 名称
    phase: Literal["scout", "designer", "builder", "tester", "seller"]
    next_agent: Optional[str]           # 下一步路由
    
    # Agent 输出
    agent_outputs: dict[str, AgentOutput]
    # {
    #   "scout": {...},
    #   "designer": {...},
    #   "builder": {...},
    #   "tester": {...},
    #   "seller": {...}
    # }
    
    # 控制
    status: Literal["idle", "running", "paused", "completed", "failed"]
    errors: list[str]                   # 错误日志
    warnings: list[str]                 # 警告信息
    
    # 上下文
    context_dir: str                    # 项目上下文目录
    messages: list                      # Agent 间的消息历史
    
    # RAG
    knowledge_hit: bool                 # 预索引是否命中
    knowledge_sources: list[str]        # 使用的知识来源
    
    # 元数据
    pipeline_id: str                    # 唯一流水线 ID
    created_at: str                     # 创建时间
    updated_at: str                     # 最后更新时间
```

### 3.2 Agent 接口协议

每个 Agent 通过 `create_react_agent` 实例化，统一接口：

```python
from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic

def create_agent(
    system_prompt: str,
    tools: list[Tool],
    model: str = "claude-sonnet-4-20250514"
) -> CompiledGraph:
    """创建 ReAct Agent 实例
    
    Args:
        system_prompt: 从 agents/templates/ 提取的角色 System Prompt
        tools: 该 Agent 可用工具列表
        model: Claude 模型名
    """
    llm = ChatAnthropic(model=model)
    return create_react_agent(llm, tools, prompt=system_prompt)
```

Agent 的输入输出规范：

```python
# 输入格式
agent_input = {
    "messages": [
        {"role": "user", "content": f"""
任务: {task_description}
上下文: {context}
上游产出: {upstream_output}
"""})
    ],
}

# 输出格式（自动从 messages 中提取最后一条 assistant 消息）
agent_output = {
    "messages": [
        # ...思维链 tool_calls ...
        {"role": "assistant", "content": "最终输出/报告内容"}
    ]
}
```

### 3.3 事件类型（SSE 推送）

```typescript
// SSE 事件协议（前后端共享）
type SSEEvent =
  | { type: "pipeline.created"; data: { pipeline_id: string; requirement: string } }
  | { type: "agent.started"; data: { agent: string; phase: string; started_at: string } }
  | { type: "agent.tool_call"; data: { agent: string; tool: string; args: any } }
  | { type: "agent.tool_result"; data: { agent: string; tool: string; summary: string } }
  | { type: "agent.completed"; data: { agent: string; output_path: string; summary: string } }
  | { type: "agent.failed"; data: { agent: string; error: string; retry_count: number } }
  | { type: "agent.retrying"; data: { agent: string; attempt: number; max_retries: number } }
  | { type: "pipeline.completed"; data: { pipeline_id: string; artifacts: string[] } }
  | { type: "pipeline.failed"; data: { pipeline_id: string; errors: string[] } }
  | { type: "knowledge.hit"; data: { source: string; page: string } }
  | { type: "knowledge.miss"; data: { query: string } };
```

---

## 四、状态流转

### 4.1 Orchestrator 状态机定义

```python
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint import MemorySaver

# Graph 定义
builder = StateGraph(PipelineState)

# 节点注册
builder.add_node("parse_requirement", parse_requirement_node)
builder.add_node("execute_scout", execute_scout_node)
builder.add_node("execute_designer", execute_designer_node)
builder.add_node("execute_builder", execute_builder_node)
builder.add_node("execute_tester", execute_tester_node)
builder.add_node("execute_seller", execute_seller_node)
builder.add_node("check_phase_complete", check_phase_complete_node)
builder.add_node("finalize_pipeline", finalize_node)

# 边定义
builder.add_edge(START, "parse_requirement")
builder.add_edge("parse_requirement", "execute_scout")

# 条件路由：按 Phase 顺序执行
builder.add_conditional_edges(
    "execute_scout",
    route_next_agent,    # → designer 或 → check_phase_complete
    {"designer": "execute_designer", "complete": "check_phase_complete"}
)
builder.add_conditional_edges(
    "execute_designer",
    route_next_agent,    # → builder
    {"builder": "execute_builder", "complete": "check_phase_complete"}
)
builder.add_conditional_edges(
    "execute_builder",
    route_next_agent,    # → tester
    {"tester": "execute_tester", "complete": "check_phase_complete"}
)
builder.add_conditional_edges(
    "execute_tester",
    route_next_agent,    # → seller
    {"seller": "execute_seller", "complete": "check_phase_complete"}
)
builder.add_conditional_edges(
    "execute_seller",
    route_next_agent,    # → end
    {"complete": "check_phase_complete"}
)

# 最终检查和输出
builder.add_conditional_edges(
    "check_phase_complete",
    should_continue,     # → finalize 或 → execute_scout (回到起点迭代)
    {"finalize": "finalize_pipeline", "continue": END}  # Phase 1 终点
)
builder.add_edge("finalize_pipeline", END)

# 编译
orchestrator = builder.compile(checkpointer=MemorySaver())
```

### 4.2 Phase 1 状态流转图

```
用户输入需求
    │
    ▼
[parse_requirement]
    ├─ 提取 project_name, project_slug
    ├─ 调用预索引门控 RAG（相关知识注入）
    └─ 设置 current_agent = "scout"
    │
    ▼
[execute_scout] ─────────────────────┐
    ├─ 创建 Scout ReAct Agent        │
    ├─ 注入 System Prompt + 工具     │
    ├─ 执行调研                      │ 失败 → 重试 (max 2次)
    ├─ 写入调研报告到 context_dir    │
    └─ status → completed/failed ────┘
    │
    ▼
[check_phase_complete]
    ├─ Phase 1 完成 → finalize
    └─ 输出结果 (调研报告路径)
```

### 4.3 Phase 2+ 完整流转图

```
parse_requirement
    │
    ▼
execute_scout ──→ 失败重试(max 2) ──→ 失败 → 记录错误 → 跳过
    │
    ▼
execute_designer ──→ 失败重试(max 2) ──→ 失败 → 记录错误 → 跳过
    │
    ▼
execute_builder ──→ 失败重试(max 2) ──→ 失败 → 记录错误 → 跳过
    │
    ▼
execute_tester ──→ 失败重试(max 2) ──→ 失败 → 记录错误 → 跳过
    │
    ▼
execute_seller ──→ 失败重试(max 2) ──→ 失败 → 记录错误 → 跳过
    │
    ▼
finalize_pipeline → 输出 artifact 清单
```

### 4.4 条件路由函数

```python
def route_next_agent(state: PipelineState) -> str:
    """决定流程走向：继续下一个 Agent 或进入检查节点"""
    current = state["current_agent"]
    agents_order = ["scout", "designer", "builder", "tester", "seller"]
    current_idx = agents_order.index(current)
    
    if current_idx + 1 < len(agents_order):
        return agents_order[current_idx + 1]
    return "complete"

def should_continue(state: PipelineState) -> str:
    """决定是否进入最终输出"""
    if state["status"] == "completed":
        return "finalize"
    return "continue"
```

---

## 五、Agent 角色定义与工具权限表

### 5.1 角色定义

| Agent | 角色 | System Prompt 来源 | 模型建议 |
|-------|------|-------------------|---------|
| **Scout** | 市场研究员 — 向外看 | `agents/templates/scout.template.md` | claude-sonnet-4-20250514 |
| **Designer** | 产品设计师 — 向内做 | `agents/templates/designer.template.md` | claude-sonnet-4-20250514 |
| **Builder** | 工程师 — 写代码 | `agents/templates/builder.template.md` | claude-sonnet-4-20250514 |
| **Tester** | QA 工程师 — 验证质量 | `agents/templates/tester.template.md` | claude-sonnet-4-20250514 |
| **Seller** | 发布经理 — 交付产出 | `agents/templates/seller.template.md` | claude-sonnet-4-20250514 |

### 5.2 工具权限矩阵

| 工具 | Scout | Designer | Builder | Tester | Seller | 用途 |
|------|:-----:|:--------:|:-------:|:------:|:------:|------|
| **search_web** | ✅ | | | | | 搜索市场信息/竞品 |
| **read_url** | ✅ | | | | | 读网页内容 |
| **read_file** | | ✅ | ✅ | ✅ | ✅ | 读上游产出文件 |
| **search_docs** | | ✅ | | | | 查技术文档/API 参考 |
| **read_design_doc** | | | ✅ | | | 读设计规格（仅 Builder） |
| **write_code** | | | ✅ | | | 生成代码文件 |
| **run_lint** | | | ✅ | | | 编译/语法检查 |
| **run_tests** | | | | ✅ | | 执行测试套件 |
| **write_fix_prompt** | | | | ✅ | | 写修复指令给 Builder |
| **read_all_outputs** | | | | | ✅ | 读全部 Agent 产出 |
| **write_readme** | | | | | ✅ | 写用户文档 |
| **generate_changelog** | | | | | ✅ | 调用 changelog-tool |
| **create_pr** | | | | | ✅ | 创建 GitHub PR |
| **write_report** | ✅ | ✅ | | | | 写调研报告/设计文档 |
| **query_knowledge** | ✅ | ✅ | ✅ | ✅ | ✅ | 查询预索引 RAG（只读） |

### 5.3 工具实现规格

```python
# 示例工具定义（使用 @tool 装饰器）

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """搜索网页获取市场/技术信息。仅 Scout 可用。
    
    Args:
        query: 搜索关键词
        max_results: 返回结果数量 (1-10)
    Returns:
        JSON 字符串：{title, url, snippet}[]
    """
    ...

@tool
def read_url(url: str) -> str:
    """读取 URL 的文本内容。仅 Scout 可用。
    
    Args:
        url: 完整 URL
    Returns:
        页面纯文本内容（自动去除 HTML 标签）
    """
    ...

@tool
def write_file(path: str, content: str) -> str:
    """写入文件到上下文目录。Agent 按角色有写入路径限制。
    
    Args:
        path: 相对路径（相对于 context_dir）
        content: 文件内容
    Returns:
        绝对路径
    """
    ...

@tool
def read_file(path: str) -> str:
    """读取文件内容。所有 Agent 可用。
    
    Args:
        path: 相对路径（相对于 context_dir）
    Returns:
        文件内容
    """
    ...

@tool
def query_knowledge(query: str) -> str:
    """查询预索引门控 RAG 系统。所有 Agent 可用。
    先匹配 index.md 索引，未命中则向量检索。
    
    Args:
        query: 查询内容
    Returns:
        知识片段列表（含来源）
    """
    ...
```

---

## 六、预索引门控 RAG 设计

### 6.1 架构

```
用户需求
    │
    ▼
┌─────────────────────────────┐
│  Step 1: 索引匹配            │
│                             │
│  需求文本 → NLP 提取关键词    │
│  → 匹配 index.md 的索引条目   │
│                             │
│  命中？                      │
│  ├─ 是 → 加载对应 wiki 页面  │
│  │       作为 Agent 上下文    │
│  └─ 否 → 进入 Step 2       │
└─────────────────────────────┘
    │ (未命中)
    ▼
┌─────────────────────────────┐
│  Step 2: 向量检索            │
│                             │
│  需求文本 → Embedding 模型    │
│  → pgvector 余弦相似度搜索    │
│  → Top-K (K=5) 片段         │
│  → 作为 Agent 上下文         │
└─────────────────────────────┘
    │
    ▼
Agent 收到增强上下文
```

### 6.2 索引匹配逻辑

```python
def match_index(requirement: str, index_path: str) -> Optional[list[str]]:
    """匹配需求到预索引条目
    
    1. 提取需求中的关键词（项目名、技术栈、领域）
    2. 与 index.md 的标题/描述匹配
    3. 命中 → 返回对应 wiki 页面路径
    4. 未命中 → 返回 None（触发向量检索）
    """
    # 简单关键词匹配（Phase 1）
    # 后续可升级为 LLM 提取关键词
    keywords = extract_keywords(requirement)
    
    with open(index_path, 'r') as f:
        content = f.read()
    
    matches = []
    for keyword in keywords:
        if keyword in content:
            # 提取相关条目
            matches.extend(find_index_entries(content, keyword))
    
    return matches if matches else None
```

### 6.3 知识库结构

| 来源 | 内容 | 索引方式 |
|------|------|---------|
| `wiki/index.md` | 全部页面的导航索引 | 直接匹配（关键词 → 页面名） |
| `wiki/entities/` | 实体（工具、人物、产品） | 向量化 |
| `wiki/concepts/` | 抽象概念和方法论 | 向量化 |
| `wiki/sources/` | 来源摘要 | 向量化 |
| `wiki/comparisons/` | 对比分析 | 向量化 |

### 6.4 已知限制（Phase 1）

- index.md 匹配是简单的子串匹配，非语义匹配
- 向量检索后不进行重排序（Phase 3 增加 Cohere Rerank）
- 知识库内容需要手动策展（Cub 维护 wiki/）

---

## 七、Agent 间通信协议

### 7.1 通信原则

1. **Agent 不直接通信** — 所有 Agent 通过 Orchestrator 管理状态
2. **上游产出是下游输入** — Designer 读 Scout 的报告，Builder 读 Designer 的规格，依此类推
3. **文件系统是共享通道** — Agent 的产出写入 context_dir，下游 Agent 通过 `read_file` 读取
4. **消息历史保留** — 所有 Agent 的 `messages` 保存在 PipelineState 中

### 7.2 上下文目录结构

```
{context_dir}/
├── requirement.txt          # 用户原始需求
├── project.json             # 解析后的项目元数据
├── scout/
│   ├── report.md            # 调研报告
│   └── sources.json         # 调研来源
├── designer/
│   ├── requirements.md      # 需求规格
│   ├── architecture.md      # 架构设计
│   └── interaction.md       # 交互设计
├── builder/
│   ├── src/                 # 源代码
│   └── package.json         # 项目配置
├── tester/
│   ├── test-plan.md         # 测试计划
│   ├── test-results.md      # 测试结果
│   └── fix-prompt.md        # 修复指令（如有）
└── seller/
    ├── README.md            # 用户文档
    ├── CHANGELOG.md         # 变更日志
    └── .github/
        └── release.yml      # 发布配置
```

---

## 八、错误处理与降级策略

| 错误场景 | 处理方式 | 恢复措施 |
|----------|---------|---------|
| Agent 超时（>5min） | 标记为 failed，记录错误 | 自动重试 1 次，仍失败则跳过 |
| LLM API 调用失败 | 捕获异常，记录 error | 重试 2 次（指数退避：1s→4s→15s） |
| 工具调用异常 | Agent 内部通过 ReAct 循环重试 | 3 次失败后返回错误消息 |
| 下游 Agent 无上游产出 | 跳过该 Agent，记录 warning | 最终输出中标注缺少的环节 |
| 并发冲突 | Python asyncio 事件循环管理 | Phase 1 单线程，无并发 |
| 磁盘写入失败 | 捕获 IOError | 重试 1 次，失败后标记 |

---

## 九、安全边界

| 维度 | 措施 |
|------|------|
| API Key 管理 | 环境变量（`ANTHROPIC_API_KEY`），不写入任何文件 |
| 文件系统 | 每个 Agent 只能在 context_dir 内写文件（通过 `write_file` 工具强制校验路径） |
| 网络访问 | Scout 的 search_web + read_url 只出不进（只读不写外部） |
| 代码执行 | Builder 不自动运行生成的代码（需用户确认），Tester 在隔离环境跑测试 |
| Prompt 注入 | 所有 Agent System Prompt 包含角色边界指令 |
