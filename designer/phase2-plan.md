# Agent Pipeline — Phase 2 详细方案

> 从 Phase 1 单 Agent 升级为 Phase 2 五 Agent LangGraph 全流水线

---

## 整体变化

```
Phase 1:                              Phase 2:

run_pipeline() 函数 (~30行)           create_orchestrator() → StateGraph (7 个节点)
    │                                     │
    ├─ parse                              ├─ parse_requirement (不变)
    ├─ match_index                        ├─ match_index (不变)
    ├─ create_scout_agent                 ├─ execute_scout (包装为 graph node)
    ├─ agent.invoke                       ├─ execute_designer (新增)
    └─ save_state                         ├─ execute_builder (新增)
                                          ├─ execute_tester (新增)
                                          │     ├─ pass → execute_seller
                                          │     └─ fail → execute_builder (回退, 最多3次)
                                          ├─ execute_seller (新增)
                                          └─ finalize (不变)

核心变化：外层 Python 函数 → LangGraph StateGraph
Agent 内层：create_react_agent 不变，从 1 个变 5 个
```

---

## 一、五个 Agent 的完整定义

### 1.1 Scout Agent（Phase 1 已完成，微调）

| 维度 | 内容 |
|------|------|
| **System Prompt 来源** | `agents/templates/scout.template.md` + 项目化 |
| **模型** | `deepseek-chat` |
| **工具** | search_web, read_url, write_report, query_knowledge |
| **输入** | `state.requirement` + `state.knowledge_context` |
| **输出** | `state.agent_outputs["scout"].output_path` → `{context_dir}/scout→designer--调研报告.md` |
| **下游读它** | Designer |

**Phase 2 微调**：Scout 的输出路径从 orchestrator 写死变为从 `state.context_dir` 动态读取，其他不变。

---

### 1.2 Designer Agent（新增）

| 维度 | 内容 |
|------|------|
| **System Prompt 来源** | `agents/templates/designer.template.md` |
| **模型** | `deepseek-chat` |
| **工具** | read_file（读 Scout 报告）, write_report（写设计文档）, query_knowledge（查内部知识） |
| **输入** | Scout 的报告内容（通过 `read_file` 工具读取 `{context_dir}/scout→designer--调研报告.md`） |
| **输出** | `{context_dir}/designer/requirements.md` + `{context_dir}/designer/architecture.md` |
| **下游读它** | Builder |

**System Prompt 核心**：

```
你是 Designer — 产品设计师。你的任务是：
1. 读 Scout 的市场调研报告
2. 写出需求分析（requirements.md）：JTBD 分析 + RICE 优先级 + MVP 功能范围
3. 写出架构设计（architecture.md）：信息架构 + 技术选型 + 数据流
4. 输出格式为 Markdown，长度不少于 800 字
5. 所有设计必须基于 Scout 报告中的数据，不凭空设计
```

**为什么只给 3 个工具**：
- Designer 的工作是"读报告 → 写设计"，不需要搜索、不需要访问外部信息
- 它的输入完全来自 Scout，不需要自己找信息——这正是 Company-OS 里 Designer "不向外搜索"的原则

---

### 1.3 Builder Agent（新增）

| 维度 | 内容 |
|------|------|
| **System Prompt 来源** | `agents/templates/builder.template.md` |
| **模型** | `deepseek-chat` |
| **工具** | read_file（读 Designer 设计）, write_code（写代码文件）, run_command（运行编译/语法检查）, query_knowledge |
| **输入** | Designer 的设计文档 + Tester 的 fix-prompt（如果有回退） |
| **输出** | `{context_dir}/builder/src/` 下的代码文件 |
| **下游读它** | Tester |

**System Prompt 核心**：

```
你是 Builder — 软件工程师。你的任务是：
1. 读 Designer 的需求分析和架构设计
2. 根据设计实现可运行的代码
3. 如果 Tester 给了 fix-prompt，根据修复指令改代码
4. 代码放在 {context_dir}/builder/src/ 下
5. 每个文件写完后标注：文件路径 + 功能说明
```

**为什么没有 search_web**：
- Builder 读 Designer 的设计即可，不需要查外部信息
- 如果真需要查技术文档，query_knowledge 够用
- 保留 run_command 做编译检查，但不能执行不可信代码

---

### 1.4 Tester Agent（新增 + 关键）

| 维度 | 内容 |
|------|------|
| **System Prompt 来源** | `agents/templates/tester.template.md` |
| **模型** | `deepseek-chat` |
| **工具** | read_file（读 Builder 代码 + Designer 设计）, run_command（运行测试）, write_report（写测试报告 + fix-prompt） |
| **输入** | Builder 的代码路径 + Designer 的设计规格 |
| **输出** | `{context_dir}/tester/test-report.md`，失败时附加 `fix-prompt.md` |
| **下游读它** | Builder（回退时）或 Seller（通过时） |

**System Prompt 核心**：

```
你是 Tester — QA 工程师。你的任务是：
1. 读 Designer 的设计规格（知道"应该做成什么样"）
2. 读 Builder 的代码（检查"实际做成了什么样"）
3. 写测试报告：逐条对照设计规格，判定 Pass/Fail
4. 如果 Fail，写 fix-prompt：哪个功能不符合设计、预期行为 vs 实际行为、修复方向
5. 判定规则：
   - 设计规格里明确的功能缺失 → Fail
   - 代码可以跑但行为不符合设计 → Fail  
   - 设计规格里没提的功能你没有代码 → 不判定（沉默即不存在）
```

---

### 1.5 Seller Agent（新增）

| 维度 | 内容 |
|------|------|
| **System Prompt 来源** | `agents/templates/seller.template.md` |
| **模型** | `deepseek-chat` |
| **工具** | read_file（读所有上游产出）, write_report（写 README/CHANGELOG）, query_knowledge |
| **输入** | 所有上游 Agent 的产出路径 |
| **输出** | `{context_dir}/seller/README.md` |
| **下游读它** | 最终用户 |

**System Prompt 核心**：

```
你是 Seller — 发布经理。你的任务是：
1. 读全部上游产出（Scout 报告 + Designer 设计 + Builder 代码 + Tester 测试报告）
2. 写 README.md：项目简介、安装方法、使用示例、架构概览
3. 写 CHANGELOG.md：基于五个 Agent 的产出，记录本次交付了什么
4. README 中英双语，至少含 3 个使用示例
```

---

## 二、Tester→Builder 回退机制

### 触发条件

Tester 的输出里包含 `fix-prompt.md` 即视为需要回退。fix-prompt 的判定标准：

| 判定 | 条件 | 示例 |
|------|------|------|
| **Pass** | 所有 Designer 明确列出的功能都有对应实现，代码可跑 | "F001 CLI入口: ✅ 存在" |
| **Fail** | 设计里明确的功能缺失、行为不符、运行报错 | "F003 状态持久化: ❌ state.json 格式与设计不符" |
| **不判定** | 设计里没提的东西，代码有没有都不管 | 沉默即不存在 |

### 回退流程

```
execute_tester 完成
    │
    ├─ fix-prompt.md 不存在 → 路由到 execute_seller（正常流程）
    │
    └─ fix-prompt.md 存在 → 检查 retry_count
           │
           ├─ retry_count < 3 → 路由回 execute_builder
           │                     Builder 读 fix-prompt → 改代码 → Tester 再测
           │
           └─ retry_count >= 3 → 路由到 execute_seller（带 warning）
                                  Seller 在 README 里标注"已知限制"
```

### 回退携带的信息

```
Builder 收到回退时，输入变为：
  "原需求：{state.requirement}
   原设计：{designer_output}
   修复指令：{tester/fix-prompt.md 的内容}
   重试次数：{state.agent_outputs["tester"].retry_count}/3"
```

---

## 三、Agent 间数据协议

### 3.1 共享数据模型（存在 PipelineState 中）

```python
# PipelineState 是全流水线共享的 dict，每个 Agent 读写自己的 slot
state = {
    "requirement": "用户原始需求",
    "project_name": "AI 提取的项目名",
    "project_slug": "文件系统 slug",
    "context_dir": "output/{slug}/",
    "current_agent": "当前运行的 agent 名",
    "knowledge_context": "预索引 RAG 的命中内容",
    
    "agent_outputs": {
        "scout": {
            "status": "completed|failed",
            "output_path": "output/{slug}/scout/report.md",
            "summary": "一句话摘要",
            "artifacts": ["文件路径列表"],
            "retry_count": 0,
            "error": null
        },
        "designer": { ... 同结构 ... },
        "builder": { ... 同结构 ... },
        "tester": { ... 同结构 ... },
        "seller": { ... 同结构 ... }
    }
}
```

### 3.2 文件命名约定

**格式：`{谁产出}→{谁读}--{什么内容}.md`**

```
output/{slug}/
├── scout→designer--调研报告.md            # Scout 产出 → Designer 读取
├── designer→builder--需求分析.md          # Designer 产出 → Builder 读取
├── designer→builder--架构设计.md          # Designer 产出 → Builder 读取
├── builder→tester--src/                   # Builder 产出 → Tester 读取（代码目录）
├── tester→builder--修复指令.md            # Tester 回退 → Builder 读取（失败时存在）
├── tester→seller--测试报告.md             # Tester 产出 → Seller 读取
└── seller→user--README.md                # Seller 产出 → 最终用户读取
```

- `→` = 数据流向，一眼看到依赖链
- `--` = 角色信息结束，内容描述开始
- 文件名自身就是流水线文档——`ls output/{slug}/` 一张图

### 3.3 每个 Agent 怎么读上游

| Agent | 读上游的方式 |
|-------|-------------|
| **Scout** | 读 `state.requirement` + `state.knowledge_context`（精确文本，不读文件） |
| **Designer** | 通过 `read_file` 工具读 `state.agent_outputs["scout"].output_path` |
| **Builder** | 读 `state.agent_outputs["designer"].output_path` + 如果有回退，读 `state.agent_outputs["tester"].fix_prompt` |
| **Tester** | 读 `state.agent_outputs["builder"].output_path` + `state.agent_outputs["designer"].output_path` |
| **Seller** | 读所有 `state.agent_outputs[*].output_path` |

### 3.3 为什么用文件系统而不是内存传数据

- 每个 Agent 是独立的 `create_react_agent` 调用，上下文不共享
- 文件系统是它们之间最可靠的共享通道
- 和 Company-OS 多 Agent 协作模型一致——文件系统即通信协议

---

## 四、LangGraph StateGraph 伪代码

```python
def create_orchestrator():
    builder = StateGraph(PipelineState)
    
    # 7 个节点
    builder.add_node("parse", parse_node)          # 解析需求 + RAG
    builder.add_node("scout", scout_node)           # Scout Agent
    builder.add_node("designer", designer_node)     # Designer Agent
    builder.add_node("builder", builder_node)       # Builder Agent
    builder.add_node("tester", tester_node)         # Tester Agent
    builder.add_node("seller", seller_node)         # Seller Agent
    builder.add_node("finalize", finalize_node)     # 收尾 + save_state
    
    # 边：线性主干
    builder.add_edge(START, "parse")
    builder.add_edge("parse", "scout")
    builder.add_edge("scout", "designer")
    builder.add_edge("designer", "builder")
    builder.add_edge("builder", "tester")
    
    # 核心：Tester → Builder 回退 vs 前进
    builder.add_conditional_edges(
        "tester",
        route_after_tester,       # 判断函数
        {
            "builder": "builder",  # 回退
            "seller": "seller",    # 前进
        }
    )
    
    builder.add_edge("seller", "finalize")
    builder.add_edge("finalize", END)
    
    return builder.compile()

def route_after_tester(state):
    """Tester 完成后，判断前进还是回退"""
    tester_output = state["agent_outputs"].get("tester", {})
    
    if tester_output.get("status") == "completed":
        return "seller"                # 通过 → 前进
    
    if tester_output.get("retry_count", 0) < 3:
        return "builder"               # 失败 → 回退（最多 3 次）
    
    return "seller"                    # 3 次重试用完 → 前进（带 warning）
```

---

## 五、和 Phase 1 的对比

| | Phase 1 | Phase 2 |
|------|---------|---------|
| **Agent 数量** | 1（Scout） | 5（Scout/Designer/Builder/Tester/Seller） |
| **编排方式** | Python 函数，直线 | LangGraph StateGraph，条件路由 |
| **失败处理** | 超时重试，直接退出 | Tester→Builder 回退循环（最多 3 次） |
| **输出** | 调研报告 | 代码 + 测试报告 + README + CHANGELOG |
| **代码改动** | orchestrator.py ~200行 | orchestrator.py 重写 + 4 个新 agent 文件 |
| **已可复用** | Scout Agent + 全部工具 + 知识模块 | ✅ 全部直接复用 |
