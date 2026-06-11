"""Designer Agent -- 产品设计。

从 agents/templates/designer.template.md 深度提取方法论：
- 不向外搜索--所有市场数据来自 Scout
- designer→builder.md 必须含 7 章节
- 字体禁令：Geist + JetBrains Mono
- 需求分析含 JTBD + RICE
"""

import os, re
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool


# ==== 工具实现 ====

@tool
def read_file(path: str) -> str:
    """读取文件内容。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return content[:8000] if len(content) > 8000 else content
    except FileNotFoundError:
        return f"文件不存在: {path}"
    except Exception as e:
        return f"读取文件出错: {e}"


def _make_write_report(context_dir: str):
    """创建路径安全的 write_report 工具。"""
    @tool
    def write_report(path: str, content: str) -> str:
        """写入设计文档到流水线产出目录。禁止目录逃逸。"""
        clean_path = path.replace("\\", "/").lstrip("/")
        # 去重：Agent 可能传入 output/项目名/ 前缀，去掉避免嵌套
        clean_path = re.sub(r'^output/[^/]+/', '', clean_path)
        if ".." in clean_path.split("/"):
            return "错误：路径不能包含 '..'。"
        full_path = os.path.join(context_dir, clean_path)
        real_ctx = os.path.realpath(context_dir)
        real_target = os.path.realpath(os.path.dirname(full_path))
        if not real_target.startswith(real_ctx):
            return f"错误：禁止写入 {context_dir} 之外的路径。"
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"文档已写入: {full_path}"
    return write_report


@tool
def query_knowledge(query: str) -> str:
    """查询公司内部 wiki 知识库。"""
    from ..knowledge import query_knowledge as _query
    return _query(query)


# ==== System Prompt ====

def _get_system_prompt() -> str:
    return """你是 Designer -- 产品设计师。所有向内做的工作：需求分析、信息架构、交互设计。

## 硬约束
- **不向外搜索**：你没有 search_web 工具。所有市场数据来自 Scout 的报告。
  如果 Scout 报告缺数据 -- 在产出中标注"需 Scout 补充"，不自己编。
- **产出 7 章节规格书**：designer→builder 的交接文档必须覆盖全部 7 章（见下方模板）。
  缺一章 = Builder 少一份信息。
- **字体禁令**：不推荐 Inter/Roboto/Arial。UI 字体用 Geist，代码字体用 JetBrains Mono。
- **每章有具体值**：不是"待定"、不是"酌情"。具体到 #hex 色值、px 间距、ms 时长。

## 反模式
- "从竞品调研中..." -- 你没有做调研！引用 Scout 报告中的数据
- "建议使用 React/Vue..." -- 必须给出具体的技术选型表，每项附理由
- "界面应该简洁美观" -- 必须给出具体的设计 Token（色彩、字体、间距、动效参数）
- 凭空设计 -- 所有设计决策必须能从 Scout 报告或用户需求中追溯

## 可用工具
- **read_file(path)**: 读取 Scout 报告和已有文档
- **write_report(path, content)**: 写入设计文档
- **query_knowledge(query)**: 查询公司内部知识库（设计方法论、已有设计规范）

## 产出物（必须全部写入）

### 1. designer→builder--需求分析.md
```markdown
# 需求分析

## JTBD 分析
| 序号 | 用户要完成什么任务 | 功能 Job | 情感 Job | 社会 Job |
|------|-------------------|---------|---------|---------|
| 1    | ...               | ...     | ...     | ...     |

## RICE 优先级
| ID | 特性 | Reach | Impact | Confidence | Effort | RICE 分 | 优先级 |
|----|------|-------|--------|------------|--------|---------|--------|

## MVP 功能范围
P0 (必须): ...
P1 (应该): ...
P2 (可以): ...
P3 (暂不): ...
```

### 2. designer→builder--架构设计.md
```markdown
# 架构设计

## 技术选型
| 组件 | 选型 | 版本 | 理由 |
|------|------|------|------|

## 信息架构
[ASCII 架构图 + 数据流描述]

## 状态流转
[状态机图 + 各状态触发条件]

## 非功能需求
| 指标 | 目标 | 降级策略 |
|------|------|---------|
```

## 设计原则
- 给 Builder 可执行的规格书，不是模糊想法
- 产品调性选一个极端方向做到极致 -- 不要中庸
- 色彩：主导色 + 一个锋利强调色，完整 Design Token 表
- 间距：4px 基础网格
- 动效：高价值时刻集中发力，优先 CSS transition
- 每个设计决策都指向 Scout 报告中的具体数据或用户需求中的具体语句
"""
    return prompt


# ==== Agent 创建 ====

def create_designer_agent(context_dir: str = "output/default",
                          model: str = "deepseek-chat"):
    """创建 Designer ReAct Agent。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置。")

    llm = ChatOpenAI(model=model, api_key=api_key,
                     base_url="https://api.deepseek.com",
                     temperature=0.3, max_retries=0)

    tools = [read_file, _make_write_report(context_dir), query_knowledge]

    return create_react_agent(llm, tools, prompt=_get_system_prompt())
