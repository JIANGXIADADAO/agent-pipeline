"""Seller Agent — 发布经理 Agent。

读取全部上游产出（Scout 报告 + Designer 设计 + Builder 代码 + Tester 测试报告），
撰写 README 和 CHANGELOG。

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
    """读取文件内容。用于读取所有上游产出物。

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
        """将文档写入文件。路径相对于流水线输出目录。

        路径示例：seller→user--README.md

        Args:
            path: 文件路径（相对于流水线输出目录）
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
        """查询内部知识库（wiki）。了解项目背景时使用。

        Args:
            query: 查询关键词或问题
        """
        from ..knowledge import query_knowledge as _query
        return _query(query)

    return query_knowledge


def _get_system_prompt() -> str:
    """构建 Seller Agent 的系统提示词。"""
    return """你是 Seller — 发布经理。

## 你的任务
1. 使用 read_file 工具读取全部上游产出物
2. 综合所有信息，使用 write_report 写入 `seller→user--README.md`
3. README 包含：项目简介、安装方法、使用示例、架构概览

## 可用工具
- **read_file(path)**: 读取文件内容
- **write_report(path, content)**: 写入文档到流水线产出目录
- **query_knowledge(query)**: 查询内部知识库

## README 要求
- 使用中文撰写
- 至少包含 3 个使用示例
- 包含安装步骤
- 说明项目架构
- 长度不少于 500 字

## 工作流程
1. 用 read_file 读取所有上游产出文件（Scout 报告、Designer 设计、Builder 代码、Tester 测试报告）
2. 综合理解项目全貌
3. 用 write_report 写入 seller→user--README.md
"""


def create_seller_agent(
    context_dir: str = "output/default",
    model: str = "deepseek-chat",
):
    """创建 Seller ReAct Agent 实例。

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
