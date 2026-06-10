# Agent Pipeline — Designer → Builder 交接

> 这是 Builder 的可执行规格书。全部 7 章，缺一章即不完整。
> Tester 也读此文档作为验收标准。

---

## 第一章：MVP 功能范围

### 1.1 RICE 优先级总表

| ID | 特性 | 阶段 | Reach | Impact | Confidence | Effort | RICE | 优先级 |
|----|------|:----:|:----:|:------:|:---------:|:-----:|:----:|:------:|
| F001 | Python Orchestrator（解析 → 调 Agent → 输出，直线流程，~30行） | P0 | 5 | 5 | 99% | 3 | 8.25 | **P0** |
| F002 | Scout Agent 实现（搜索 + 读网页 + 写报告） | P0 | 5 | 5 | 99% | 3 | 8.25 | **P0** |
| F003 | CLI 入口（`agent-pipeline run <requirement>`） | P0 | 4 | 4 | 95% | 5 | 3.04 | **P0** |
| F011 | Agent 间上下文传递 + 消息缓存 | P1 | 5 | 5 | 95% | 3 | 7.92 | **P1** |
| F013 | Agent 失败重试 + 超时处理 | P1 | 5 | 5 | 90% | 3 | 7.50 | **P1** |
| F004-F007 | Designer / Builder / Tester / Seller Agent | P1 | 4 | 4-5 | 85-90% | 3-4 | ~4.5 | **P1** |
| F008 | Web UI Pipeline 可视化（SSE 集成） | P1 | 5 | 4 | 95% | 4 | 4.75 | **P1** |
| F012 | SSE 实时推送 | P1 | 5 | 4 | 95% | 5 | 3.80 | **P1** |
| F009 | 预索引门控 RAG | P2 | 4 | 4 | 80% | 5 | 2.56 | **P2** |
| F013-F016 | 评估 / 护栏 / CHANGELOG / PR | P2-P3 | 3-4 | 3-4 | 60-90% | 3-6 | 1.6-2.8 | **P2-P3** |

### 1.2 Phase 分阶段

| 阶段 | 特性 | 核心交付 | 用户可见效果 |
|------|------|---------|------------|
| **Phase 1** (P0) | F001 + F002 + F003 | Orchestrator + Scout 单 Agent, CLI 可跑 | `agent-pipeline run "需求"` → 输出调研报告 |
| **Phase 2** (P1) | F004-F008 + F011-F013 | 五 Agent 完整流水线 + Web UI | 浏览器输入需求，看 5 Agent 依次协作 |
| **Phase 3** (P2) | F009 + F014-F017 | 预索引 RAG + 评估 + 输出层 | 内部知识优化质量 + LLM 评分 |
| **Phase 4** (P3) | F018-F022 | 跳过重跑 + Docker + 多轮对话 | 可部署、可交互的生产化系统 |
| **Phase 5** (P4-P5) | F023-F025 | 自定义 Agent + 多租户 | 平台级产品 |

### 1.3 Phase 1 MVP 精确范围

**In Scope（必须实现）**：
1. **Orchestrator**：Python 函数（~30行）接收用户需求 → 解析提取项目信息 → 调用预索引门控 RAG（index.md 关键词匹配）→ 创建 Scout ReAct Agent → 等待完成 → 写 state.json → 输出结果
2. **Scout Agent**：用 `create_react_agent` 创建，绑定 `search_web` + `read_url` + `write_report` + `query_knowledge` 工具
3. **CLI 入口**：`agent-pipeline run "需求"`，支持 `--resume` 断点恢复
4. **状态持久化**：`state.json`（JSON 文件），每次状态变更后写入
5. **简单重试**：Agent 超时 5 分钟后自动重试 1 次
6. **基础错误处理**：LLM API 失败 → 指数退避重试（1s→4s→15s）→ 3 次后报告用户

**Out of Scope（Phase 2）**：
- 其他 4 个 Agent
- Web UI
- SSE 推送
- 多轮对话
- 预索引 RAG（Phase 1 先做 index.md 关键词匹配作为简化版）

---

## 第二章：技术架构

### 2.1 ASCII 架构总图

```
                              ┌──────────────────────┐
                              │   User / CLI           │
                              │  agent-pipeline run    │
                              └──────────┬───────────┘
                                         │ 需求文本
                                         ▼
┌────────────────────────────────────────────────────────────────────┐
│                      Agent Pipeline Core (Python)                   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │          Orchestrator（Python 函数，~30 行，无 LangGraph）     │   │
│  │                                                              │   │
│  │  parse_requirement → match_index_knowledge →                 │   │
│  │  create_scout_agent() → agent.invoke() → save_state()        │   │
│  │                                                              │   │
│  │  Phase 1: 直线流程，无分支。Phase 2+ 升级为 StateGraph。      │   │
│  └──────────────────────────┬───────────────────────────────────┘   │
│                             │ 调用                                  │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │       Scout ReAct Agent (create_react_agent)                 │   │
│  │                                                              │   │
│  │  System Prompt: agents/templates/scout.template.md          │   │
│  │  Tools: search_web, read_url, write_report, query_knowledge │   │
│  │  ReAct: Think → Tool Call → Observe → ... → Final          │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                             │                                       │
│                             ▼                                       │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │       预索引门控 RAG（Phase 1：index.md 子串匹配）             │   │
│  │                                                              │   │
│  │  requirement → index.md keyword match                        │   │
│  │    ├─ HIT  → load wiki pages directly                        │   │
│  │    └─ MISS → "knowledge_source: none"                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                     Context Directory (文件系统)                     │
│                                                                      │
│  {pipeline_dir}/                                                    │
│  ├── requirement.txt           # 原始需求                          │
│  ├── project.json              # 元数据                            │
│  ├── state.json                # 流水线状态（断点恢复）             │
│  └── scout/report.md           # 调研报告                          │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈选型

| 组件 | 选型 | 理由 |
|------|------|------|
| **语言** | Python 3.12+ | 项目既定。LangGraph 官方语言，类型提示增强 |
| **编排层 (Phase 1)** | Python 函数 | 直线流程无需状态机。~30行。Phase 2+ 升级为 LangGraph StateGraph |
| **编排层 (Phase 2+)** | LangGraph ≥0.2.0 | 条件路由（Tester→Builder回退）、Checkpoint持久化。Phase 1 不引入 |
| **Agent 内层** | `langgraph.prebuilt.create_react_agent` | 官方 ReAct 实现，内置 ToolNode + 消息循环。减少自维护 Bug |
| **LLM SDK** | `anthropic` ≥0.40.0 | 项目既定。Claude tool use 稳定性行业领先 |
| **CLI 框架** | `click` ≥8.1 | Python 生态最成熟 CLI 库。参数校验自动完成 |
| **向量数据库** | `pgvector` (via `psycopg2` + `pgvector`) | 开源无锁定。与 Supabase 生产兼容。Phase 1 可选 SQLite 替代 |
| **Embeddings** | `voyage-2` 或 `text-embedding-3-small` | 常用嵌入模型，配合 pgvector 效果良好 |
| **Web UI** | Next.js ≥14（复用 agent-team-dashboard） | 项目既定。已有 SSE 推送 + Pipeline 可视化组件 |
| **SSE** | Server-Sent Events（Python `sse-starlette`） | 单向推送适合流水线状态更新。已有 agent-team-dashboard 集成经验 |
| **状态持久化** | JSON 文件（Phase 1）→ PostgreSQL（Phase 3） | Phase 1 零数据库依赖。JSON 足够单 Agent 状态 |
| **HTTP 服务** | FastAPI（Phase 2 起） | 异步支持好，自动生成 OpenAPI 文档。与 SSE 兼容 |
| **包管理** | `uv` / `pip` + `requirements.txt` | 简单直接，降低贡献门槛 |

### 2.3 关键依赖清单（Phase 1）

```
langgraph>=0.2.0
langchain-anthropic>=0.2.0
anthropic>=0.40.0
click>=8.1.0
httpx>=0.27.0          # 用于 search_web + read_url 工具
beautifulsoup4>=4.12.0 # 用于 HTML 解析
```

---

## 第三章：组件规格

### 3.1 Orchestrator 实现（Phase 1：Python 函数）

```python
# === src/lib/orchestrator.py ===

from dataclasses import dataclass, field
from typing import Optional, Literal
import json, os, uuid
from datetime import datetime, timezone

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
    agent_outputs: dict = field(default_factory=dict)
    status: str = "idle"
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    context_dir: str = ""
    knowledge_hit: bool = False
    knowledge_sources: list = field(default_factory=list)
    pipeline_id: str = ""
    created_at: str = ""
    updated_at: str = ""

def run_pipeline(requirement: str) -> PipelineState:
    """Phase 1 Orchestrator：直线流程，~30 行，无 LangGraph 外层"""
    
    state = PipelineState(requirement=requirement)
    state.pipeline_id = f"pl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    state.project_name = extract_project_name(requirement)
    state.project_slug = slugify(state.project_name)
    state.context_dir = f"output/{state.project_slug}"
    state.status = "running"
    state.created_at = datetime.now(timezone.utc).isoformat()
    
    os.makedirs(state.context_dir, exist_ok=True)
    
    # Step 1: 预索引门控 RAG（index.md 子串匹配）
    state = match_index_knowledge(state, index_path="wiki/index.md")
    
    # Step 2: 创建并运行 Scout Agent
    agent = create_scout_agent()
    
    state.agent_outputs["scout"] = AgentOutput(
        status="running",
        started_at=datetime.now(timezone.utc).isoformat()
    )
    
    try:
        result = agent.invoke({
            "messages": [{
                "role": "user",
                "content": f"需求：{state.requirement}\n\n请进行市场调研，输出报告到 {state.context_dir}/scout/report.md"
            }]
        })
        
        state.agent_outputs["scout"].status = "completed"
        state.agent_outputs["scout"].completed_at = datetime.now(timezone.utc).isoformat()
        state.agent_outputs["scout"].output_path = f"{state.context_dir}/scout/report.md"
        state.agent_outputs["scout"].summary = "调研报告已生成"
        state.agent_outputs["scout"].raw_output = result["messages"][-1].content
        
    except Exception as e:
        state.agent_outputs["scout"].status = "failed"
        state.agent_outputs["scout"].error = str(e)
        state.status = "failed"
        state.errors.append(str(e))
    
    # Step 3: 持久化状态
    state.status = "completed" if state.agent_outputs["scout"].status == "completed" else "failed"
    save_state(state)
    
    return state
```

### 3.2 Agent 实现模式（Phase 1：独立函数，Phase 2+ 包装为 StateGraph 节点）

```python
# === src/lib/agents/scout_agent.py ===

from langgraph.prebuilt import create_react_agent
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """搜索网页获取市场/技术信息。仅 Scout 可用。"""
    # 使用 httpx 调用搜索 API
    ...

@tool
def read_url(url: str) -> str:
    """读取 URL 的文本内容。"""
    # 使用 httpx + BeautifulSoup
    ...

@tool
def write_report(path: str, content: str) -> str:
    """写入调研报告。"""
    ...

@tool
def query_knowledge(query: str) -> str:
    """查询预索引门控 RAG。"""
    ...

def create_scout_agent():
    """创建 Scout ReAct Agent 实例"""
    llm = ChatAnthropic(model="claude-sonnet-4-20250514")
    tools = [search_web, read_url, write_report, query_knowledge]
    
    system_prompt = """你是 Scout — 市场研究员。
你的任务是根据用户需求进行市场调研，输出结构化调研报告。
    
你可用的工具：
- search_web(query): 搜索互联网
- read_url(url): 读取网页内容
- write_report(path, content): 写入调研报告
- query_knowledge(query): 查询知识库

调研报告必须包含：市场概述、竞品分析、用户画像、赛道空白、技术趋势。
"""

    return create_react_agent(llm, tools, prompt=system_prompt)

def execute_scout_phase2(state: PipelineState) -> PipelineState:
    """Phase 2+ Scout 执行节点（LangGraph StateGraph 节点函数）。
    Phase 1 直接在 orchestrator 中调用 create_scout_agent().invoke()，不用这个包装器。"""
    agent = create_scout_agent()
    
    # 准备输入
    requirement = state["requirement"]
    context_dir = state["context_dir"]
    
    # 执行 Agent
    result = agent.invoke({
        "messages": [{
            "role": "user",
            "content": f"需求：{requirement}\n\n请进行市场调研，输出报告到 {context_dir}/scout/report.md"
        }]
    })
    
    # 更新状态
    state["agent_outputs"]["scout"] = {
        "status": "completed",
        "output_path": f"{context_dir}/scout/report.md",
        "summary": "市场调研报告已生成",
        "raw_output": result["messages"][-1].content,
        "started_at": "...",
        "completed_at": "...",
        "error": None,
        "retry_count": 0,
        "artifacts": [f"{context_dir}/scout/report.md"]
    }
    
    return state
```

### 3.3 五个 Agent 的 System Prompt 模板

**System Prompt 应从 `agents/templates/*.template.md` 提取核心指令，结合项目特定上下文构建。**
以下为简化版，Builder 需读取模板文件后展开。

| Agent | System Prompt 核心内容 | 注入的上下文 |
|-------|----------------------|-------------|
| Scout | 你是 Scout — 市场研究员。搜索竞品/技术/方案，输出结构化调研报告。 | 用户需求 |
| Designer | 你是 Designer — 产品设计师。基于调研报告做需求分析、信息架构、交互设计。 | Scout 报告路径 |
| Builder | 你是 Builder — 工程师。基于设计规格写代码、跑编译检查。 | Designer 文档路径 |
| Tester | 你是 Tester — QA 工程师。读代码写测试、跑测试套件、输出 fix-prompt。 | Builder 代码路径 |
| Seller | 你是 Seller — 发布经理。读全部产出、写 README/CHANGELOG、创建 PR。 | 所有 Agent 产出路径 |

### 3.4 Web UI 线框图

```
=== Phase 2 Web UI ===

页面左侧：流水线看板
┌─────────────────────────────────────────┐
│  Agent Pipeline                    ⚙️    │
│  多 Agent 开发流水线                     │
├─────────────────────────────────────────┤
│ ┌─── 输入区 ──────────────────────────┐ │
│ │ 描述你的产品需求...                    │ │
│ │                                      │ │
│ │ [▶ 启动流水线]   [📋 示例需求]        │ │
│ └──────────────────────────────────────┘ │
│ ┌─── 流水线看板 ──────────────────────┐ │
│ │ ┌────┐   ┌────┐   ┌────┐   ┌────┐  │ │
│ │ │Scout│ → │Dsgn│ → │Buil│ → │Test│  │ │
│ │ │ ✅  │   │ ▶  │   │ ⏳  │   │ ⏳  │  │ │
│ │ └────┘   └────┘   └────┘   └────┘  │ │
│ │               ┌────┐               │ │
│ │               │Sell│               │ │
│ │               │ ⏳  │               │ │
│ │               └────┘               │ │
│ │ 总进度: ████░░░░░░ 40%             │ │
│ └──────────────────────────────────────┘ │
│ ┌─── 输出区 ──────────────────────────┐ │
│ │ 📁 scout/report.md    ✅ 12KB       │ │
│ │ 📁 designer/          ▶ 进行中      │ │
│ │ ...                                 │ │
│ │ [📥 下载全部]                        │ │
│ └──────────────────────────────────────┘ │
└─────────────────────────────────────────┘

右侧：详情面板（点击卡片后弹出）
┌──────────────────────────────────────┐
│ Scout Agent 执行详情             [✕] │
│ 状态: ✅ 已完成 · 耗时: 1m30s        │
├──────────────────────────────────────┤
│ [对话] [产出物] [耗时分析]            │
├──────────────────────────────────────┤
│ 用户 → 请调研 AI 编码助手市场         │
│                                      │
│ Scout → search_web("AI coding 2026") │
│   ✅ 5 个来源                          │
│                                      │
│ Scout → read_url("https://...")      │
│   ✅ 读取成功 (12KB)                  │
│                                      │
│ Scout → write_report("report.md")    │
│   ✅ 已写入                           │
│                                      │
│ 最终报告摘要: [展开]                  │
└──────────────────────────────────────┘
```

### 3.5 关键交互序列

**Phase 1 CLI 交互：**
```
$ agent-pipeline run "调研 AI 编码助手市场"
🚀 流水线已启动 (ID: pl_20260610_001)
📋 需求: 调研 AI 编码助手市场
📁 项目: ai-coding-assistant-market-research

▶ Phase: Scout Agent
  ⏳ 正在搜索...
  ✅ search_web("AI coding assistant market 2026")
  ⏳ 正在分析...
  ✅ read_url("https://example.com/report")
  ⏳ 正在撰写报告...
  ✅ 调研报告已生成: output/scout/report.md

✅ 流水线完成 (总耗时: 2m15s)
📄 产出物:
  - output/scout/report.md (8KB)
```

**Phase 2 Web UI 交互：**
1. 用户打开 `http://localhost:3000`
2. 输入需求 → 点击"启动流水线"
3. Scout 卡片从 idle → running 动画（蓝色高亮）
4. 工具调用实时出现在卡片下方
5. Scout 完成 → 卡片绿色 ✅ → 流向 Designer
6. 依此类推至 Seller
7. 全部完成 → 列表展示所有产出物 → 可下载

---

## 第四章：设计 Token

### 4.1 色彩系统

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-primary` | `#2563EB` | 主色 — 按钮、链接、激活态 |
| `--color-primary-hover` | `#1D4ED8` | 主色 Hover |
| `--color-success` | `#16A34A` | 成功 — Agent 完成、测试通过 |
| `--color-warning` | `#F59E0B` | 警告 — Agent 重试、降级 |
| `--color-error` | `#DC2626` | 错误 — Agent 失败、API 错误 |
| `--color-neutral-50` | `#F9FAFB` | 页面背景 |
| `--color-neutral-100` | `#F3F4F6` | 卡片背景 |
| `--color-neutral-200` | `#E5E7EB` | 边框、分割线 |
| `--color-neutral-500` | `#6B7280` | 辅助文本 |
| `--color-neutral-700` | `#374151` | 正文文本 |
| `--color-neutral-900` | `#111827` | 标题文本 |
| `--color-agent-scout` | `#8B5CF6` | Scout 品牌色 — 紫色 |
| `--color-agent-designer` | `#3B82F6` | Designer 品牌色 — 蓝色 |
| `--color-agent-builder` | `#10B981` | Builder 品牌色 — 绿色 |
| `--color-agent-tester` | `#F59E0B` | Tester 品牌色 — 橙色 |
| `--color-agent-seller` | `#EC4899` | Seller 品牌色 — 粉色 |
| `--color-running` | `#3B82F6` | 运行中状态指示 |
| `--color-completed` | `#16A34A` | 已完成状态指示 |

### 4.2 字体系统

| Token | 值 | 用途 |
|-------|-----|------|
| `--font-sans` | `'Geist', system-ui, sans-serif` | 界面文本 — 正文、标题、按钮 |
| `--font-mono` | `'JetBrains Mono', monospace` | 代码文本 — CLI 输出、工具调用记录 |
| `--font-size-xs` | `0.75rem` (12px) | 辅助信息 |
| `--font-size-sm` | `0.875rem` (14px) | 小字、状态标签 |
| `--font-size-base` | `1rem` (16px) | 正文 |
| `--font-size-lg` | `1.125rem` (18px) | 小标题 |
| `--font-size-xl` | `1.25rem` (20px) | 卡片标题 |
| `--font-size-2xl` | `1.5rem` (24px) | 页面标题 |

### 4.3 间距系统（4px 网格）

| Token | 值 | 用途 |
|-------|------|------|
| `--space-1` | `4px` | 微间距 |
| `--space-2` | `8px` | 紧密间距 — 图标与文字 |
| `--space-3` | `12px` | 内间距 — 输入框 padding |
| `--space-4` | `16px` | 标准间距 — 卡片内边距 |
| `--space-5` | `20px` | 大间距 — 区域间隔 |
| `--space-6` | `24px` | 段落间距 |
| `--space-8` | `32px` | 大区域间隔 |
| `--space-10` | `40px` | 页面 section 间隔 |

### 4.4 动效参数

| Token | 值 | 用途 |
|-------|------|------|
| `--transition-fast` | `150ms ease-in-out` | Hover / 点击反馈 |
| `--transition-normal` | `300ms ease-in-out` | 卡片状态切换 |
| `--transition-slow` | `500ms ease-in-out` | 面板展开/折叠 |
| `--spring-bounce` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | 产出物出现动画 |
| `--duration-shake` | `500ms` | 错误抖动 |
| `--duration-pulse` | `1.5s ease-in-out infinite` | 加载骨架脉冲 |

---

## 第五章：非功能需求

### 5.1 性能目标

| 指标 | Phase 1 目标 | Phase 2+ 目标 |
|------|:-----------:|:-------------:|
| 端到端运行时间（单 Agent） | ≤ 5 分钟 | ≤ 10 分钟（5 Agent） |
| CLI 启动时间（冷启动） | ≤ 3 秒 | ≤ 3 秒 |
| Web UI 首屏加载 | — | ≤ 2 秒 |
| SSE 事件推送延迟 | — | ≤ 500ms |
| 状态持久化写入 | ≤ 100ms | ≤ 100ms |
| 工具调用响应时间（search_web） | ≤ 10 秒 | ≤ 10 秒 |
| 并发流水线 | 1（单线程） | 3（asyncio） |

### 5.2 降级策略

| 场景 | 降级行为 | 用户提示 |
|------|---------|---------|
| LLM API 超时（>30s） | 重试 2 次（1s→4s 退避），第 3 次失败标记 | "LLM 服务暂时不可用，已自动重试。重试 {n}/3" |
| LLM API 返回空 | 重新调用 1 次，仍为空则标记失败 | "Agent 返回空结果，请检查需求描述是否清晰" |
| search_web 失败 | 跳过搜索，直接输出"搜索服务不可用，使用已有知识" | "搜索服务暂时不可用，使用已有知识库回答" |
| read_url 失败 | 跳过该 URL，继续处理其他来源 | "部分网页读取失败 (2/5)，已跳过" |
| 状态文件写入失败 | 重试 1 次，仍失败则输出到 stdout 并提示 | "状态持久化失败，当前进度仅存在于内存中" |
| No API Key | 立即报错，不启动流水线 | "请设置 ANTHROPIC_API_KEY 环境变量" |
| 磁盘空间不足 | 检测可用空间 < 100MB 时提前报错 | "磁盘空间不足，请清理后重试" |

### 5.3 Agent 失败处理

| 失败类型 | 检测方式 | 处理动作 | 最终状态 |
|----------|---------|---------|---------|
| Agent 超时 | 计时器 > max_duration（默认 5min） | 重试 1 次，仍超时则标记 failed | `failed` + 错误消息"执行超时" |
| LLM 调用异常 | `try/except` 捕获 `anthropic.APIError` | 重试 2 次（指数退避） | 3 次失败后 `failed` |
| 工具调用异常 | Agent 内部 ReAct 循环检测 | Agent 重试最多 3 次 | `failed` + 工具名 + 错误 |
| 空输出 | 检查消息长度 / 文件大小 | 重新执行 1 次 | `failed` + "产出为空" |
| 下游 Agent 无上游输入 | 检查上游 `agent_outputs` | 跳过该 Agent，记录 warning | `skipped` |

### 5.4 安全要求

| 要求 | 实现方式 |
|------|---------|
| API Key 不落地 | 仅从环境变量读取，不写入任何文件 |
| 工具路径隔离 | `write_file` 工具强制校验路径前缀，只能在 context_dir 内写入 |
| 无自动代码执行 | Builder 只写代码不执行（用户手动执行） |
| Tester 隔离测试 | Tester 在临时目录跑测试，不影响系统文件 |
| .gitignore | 忽略 `output/`、`state.json`、`.env` |

### 5.5 兼容性

| 维度 | 要求 |
|------|------|
| Python 版本 | 3.12+ |
| 操作系统 | macOS / Linux / Windows (WSL 推荐) |
| 浏览器（Web UI） | Chrome 120+, Firefox 120+, Safari 17+ |
| Node.js（Web UI） | ≥18 |

---

## 第六章：给 Tester 的测试要点

> 此章节是 Tester 写测试计划和 E2E 测试的依据。每条测试要点应产生至少一个测试用例。

### 6.1 功能正向（Phase 1 — 必须覆盖）

| ID | 场景 | 输入 | 预期输出 |
|----|------|------|---------|
| T1.1 | 标准需求运行 | `agent-pipeline run "调研 AI 编码助手市场"` | Scout 输出报告到 `output/{slug}/scout/report.md` |
| T1.2 | 短需求 | `agent-pipeline run "分析竞品"` | 运行成功，报告内容完整 |
| T1.3 | 带特符需求 | `agent-pipeline run "调研 Python 3.12 的 match-case 语法在 Agent 框架中的应用"` | 项目名正确生成，运行成功 |
| T1.4 | 查看状态 | `agent-pipeline status` | 显示当前阶段、耗时、已完成 Agent |
| T1.5 | 列出历史 | `agent-pipeline list` | 显示历史流水线列表 |

### 6.2 功能异常（必须覆盖）

| ID | 场景 | 输入/条件 | 预期行为 |
|----|------|----------|---------|
| T2.1 | 空需求 | `agent-pipeline run ""` | 报错："需求不能为空" |
| T2.2 | 仅空格需求 | `agent-pipeline run "   "` | 报错："需求不能为空" |
| T2.3 | 超长需求 | `agent-pipeline run "..." (10000+ 字符)` | 截断或正常处理 |
| T2.4 | 无 API Key | 环境变量 ANTHROPIC_API_KEY 未设置 | "请设置 ANTHROPIC_API_KEY" |
| T2.5 | API Key 无效 | ANTHROPIC_API_KEY=invalid_key | "API Key 认证失败" |
| T2.6 | 网络断开 | 运行中拔掉网线 | 超时后报错："网络连接失败" |
| T2.7 | 非法命令 | `agent-pipeline unknown` | "未知命令: unknown" |
| T2.8 | --resume 但无历史 | `agent-pipeline run --resume` | "没有找到可恢复的流水线" |

### 6.3 边界条件

| ID | 场景 | 条件 | 预期行为 |
|----|------|------|---------|
| T3.1 | 最小需求 | 正好 10 个字符 | 正常运行 |
| T3.2 | 最大需求 | 4096 字符 | 正常运行 |
| T3.3 | 极快完成 | LLM 返回空（模拟） | 重试后标记 failed |
| T3.4 | 多字节字符 | 中/日/韩/emoji 混合需求 | 正常运行，文件名正确处理 |
| T3.5 | 并发 status 调用 | 流水线运行中执行 `agent-pipeline status` × 10 | 始终返回当前正确状态 |
| T3.6 | 重复运行 | 同一需求运行两次 | 第二次创建新项目（加时间戳） |

### 6.4 Agent 行为验证

| ID | 场景 | 验证方法 |
|----|------|---------|
| T4.1 | Scout 调用 search_web | 检查 tools 日志包含 search_web 调用 |
| T4.2 | Scout 输出报告格式 | 报告包含"市场概述"段落 |
| T4.3 | Agent 超时重试 | 设置短超时 → 确认重试执行 |
| T4.4 | Agent 最大重试次数耗尽 | 设置极短超时 → 确认 max_retries 后 failed |
| T4.5 | 工具调用失败 | 模拟 read_url 失败 → Agent 正常处理 |

### 6.5 故障场景（具体到数量级）

| ID | 场景 | 条件 | 预期行为 |
|----|------|------|---------|
| T5.1 | Orchestrator 某 Agent 超时 | Scout Agent 耗时 > 5min | 自动重试 1 次，仍超时 → 标记 failed |
| T5.2 | Tester 打回 Builder 循环 | Tester 发现 bug → Builder 修复 → Tester 再测 | Phase 2: 支持最多 3 次修复循环 |
| T5.3 | 空需求输入 | 需求字符串为空/仅空白 | 立即返回错误，不创建流水线 |
| T5.4 | LLM 返回格式异常 | Scout 输出非 markdown | Agent 自动修正 1 次 |
| T5.5 | 状态文件损坏 | 手动修改 state.json 为非法 JSON | `--resume` 时检测到损坏 → 提示手动修复 |
| T5.6 | 多 Agent 全部跳过 | 所有 Agent 都 failed | 最终输出"流水线未完成"，显示各 Agent 错误 |

### 6.6 CLI 输出一致性验证

| ID | 验证点 | 预期 |
|----|--------|------|
| T6.1 | 启动输出 | 包含 "🚀" / "流水线已启动" / Pipeline ID |
| T6.2 | 进度输出 | 每个 Agent 执行时显示当前 Agent 名称 |
| T6.3 | 完成输出 | 包含 "✅" / "流水线完成" / 总耗时 / 产出物列表 |
| T6.4 | 失败输出 | 包含 "❌" / 失败原因 / 可恢复操作提示 |
| T6.5 | 空输出不出现 | 无任何 `None`/`undefined`/空行异常 |

---

## 第七章：产品文档要点

### 7.1 必需文档（Seller 产出前，Builder 先补充）

| 文档 | 文件路径 | 内容 | 读者 |
|------|---------|------|------|
| CLI 参考 | `builder/cli-reference.md` | 每个命令的用途、参数、示例 | Tester + Seller |
| 架构设计 | `designer/architecture.md` | 双层架构、数据模型、状态流转 | Builder 自己 + 开源贡献者 |
| 交互设计 | `designer/interaction.md` | Web UI 交互流程、状态定义 | Builder（Web UI 实现） |
| 需求分析 | `designer/requirements.md` | JTBD + RICE 优先级 | 所有 Worker |

### 7.2 Seller 产出文档

| 文档 | 文件路径 | 内容来源 |
|------|---------|---------|
| README (英文) | `seller/readme.md` → `README.md` | CLI 参考 + Tester 示例 |
| README (中文) | `seller/readme.zh.md` → `README.zh.md` | 英文版翻译 |
| Quick Start | `seller/quickstart.md` | 最简上手路径（30 秒） |
| Landing Page | `seller/landing-page.md` | 价值主张 + Demo/GIF + FAQ |
| 发布检查清单 | `seller/launch-checklist.md` | 发布前逐条检查 |

### 7.3 README 必须覆盖的路径

| 路径 | 适用用户 | 步骤数 |
|------|---------|:------:|
| 零配置路径 | 只想看看效果的用户 | ≤ 3 步 |
| 有 API Key 路径 | 准备正式使用的用户 | ≤ 3 步 |
| Web UI 路径 | 喜欢图形界面的用户 | ≤ 3 步 |
| 开发者/贡献路径 | 想改代码/提 PR 的用户 | 5-7 步 |

### 7.4 架构文档（供开源社区）

| 文档 | 内容 |
|------|------|
| `ARCHITECTURE.md` | 双层架构图解、数据流、Agent 权限表 |
| `CONTRIBUTING.md` | 贡献指南、代码规范、PR 流程 |
| `CHANGELOG.md` | 版本历史（由 changelog-tool 生成） |
| `LICENSE` | MIT（建议） |

### 7.5 文档质量要求

| 维度 | 标准 |
|------|------|
| 语言 | README 中英双语，其余文档英文 |
| 示例 | 每个命令至少 1 个带输出的完整示例 |
| 截图 | Web UI 至少 3 张截图（首页、运行中、完成） |
| 术语表 | 首次使用术语时给出解释 |
| 故障排除 | 至少覆盖 5 个常见问题 |

---

*以上 7 章涵盖全部设计规格。Builder 按 P0 → P1 → P2 顺序实现。*
*实现中的技术偏差记录到 `builder→tester.md`。*
