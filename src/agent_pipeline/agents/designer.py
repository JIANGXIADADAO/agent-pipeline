"""Designer Agent — 产品设计师 Agent。

基于 Scout 调研报告，产出需求分析和架构设计文档。

工具：read_file, write_report, query_knowledge
模型：DeepSeek (ChatOpenAI)
"""

import os
from pathlib import Path
from typing import Optional

from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool


# ---- 工具实现 ----


@tool
def read_file(path: str) -> str:
    """读取文件内容。用于读取上游 Agent 的产出文件。

    Args:
        path: 文件的完整路径
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content:
            return "文件内容为空。"
        if len(content) > 8000:
            return content[:8000] + "\n\n...（内容已截断，全文过长）"
        return content
    except FileNotFoundError:
        return f"错误：文件不存在 {path}"
    except Exception as e:
        return f"读取文件失败：{e}"


def _make_write_report(context_dir: str):
    """创建一个绑定 context_dir 的 write_report 工具。"""

    @tool
    def write_report(path: str, content: str) -> str:
        """将设计文档写入文件。路径相对于流水线输出目录，禁止写入其他位置。

        Args:
            path: 文件路径（相对于流水线输出目录），如 "designer→builder--需求分析.md"
            content: 文件内容（Markdown 格式）
        """
        clean_path = path.replace("\\", "/").lstrip("/")
        if ".." in clean_path.split("/"):
            return "错误：路径不能包含 '..'（禁止目录逃逸）。"

        full_path = os.path.join(context_dir, clean_path)
        real_context = os.path.realpath(context_dir)
        real_target = os.path.realpath(os.path.dirname(full_path))

        if not real_target.startswith(real_context):
            return f"错误：禁止写入 {context_dir} 之外的路径。"

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = os.path.getsize(full_path)
        return (
            f"文件已成功写入：{full_path}\n"
            f"文件大小：{file_size} 字节\n"
            f"相对路径：{clean_path}"
        )

    return write_report


def _make_query_knowledge():
    """创建 query_knowledge 工具。"""

    @tool
    def query_knowledge(query: str) -> str:
        """查询内部知识库（wiki）。需要了解内部已有知识时使用。

        Args:
            query: 查询关键词或问题
        """
        from ..knowledge import query_knowledge as _query
        return _query(query)

    return query_knowledge


def _get_system_prompt() -> str:
    """构建 Designer Agent 的系统提示词。"""
    return """你是 Designer — 产品设计师。

## 你的任务
1. 使用 read_file 工具读取 Scout 的市场调研报告
2. 写出需求分析（`designer→builder--需求分析.md`）：
   - JTBD 分析（用户要完成什么任务）
   - RICE 优先级表
   - MVP 功能范围
3. 写出架构设计（`designer→builder--架构设计.md`）：
   - 信息架构
   - 技术选型
   - 数据流设计
4. 使用 write_report 工具写入文件

## 可用工具
- **read_file(path)**: 读取文件内容
- **write_report(path, content)**: 写入设计文档到流水线产出目录
- **query_knowledge(query)**: 查询内部知识库

## 设计原则
- 所有设计必须基于 Scout 报告中的数据，不凭空设计
- 需求分析至少 500 字
- 架构设计至少 500 字
- 使用 Markdown 格式
- 输出中文文档

## 工作流程
1. 先用 read_file 读取 Scout 报告（路径会在用户消息中提供）
2. 必要时用 query_knowledge 查询内部知识
3. 用 write_report 分别写入需求分析和架构设计
"""


def create_designer_agent(
    context_dir: str = "output/default",
    model: str = "deepseek-chat",
):
    """创建 Designer ReAct Agent 实例。

    Args:
        context_dir: 流水线上下文目录（路径隔离）
        model: DeepSeek 模型名称
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置。请设置: export DEEPSEEK_API_KEY=sk-xxx")

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=0.3,
        max_retries=0,
    )

    tools = [
        read_file,
        _make_write_report(context_dir),
        _make_query_knowledge(),
    ]

    system_prompt = _get_system_prompt()

    return create_react_agent(llm, tools, prompt=system_prompt)
