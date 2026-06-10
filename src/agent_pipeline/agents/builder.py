"""Builder Agent — 软件工程师 Agent。

基于 Designer 的架构设计，实现可运行的代码。
如果 Tester 提供了 fix-prompt，根据修复指令改代码。

工具：read_file, write_code, run_command, query_knowledge
模型：DeepSeek (ChatOpenAI)
"""

import os
import subprocess
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


def _make_write_code(context_dir: str):
    """创建一个绑定 context_dir 的 write_code 工具。
    代码写入 {context_dir}/builder→tester--src/ 目录下。
    """

    @tool
    def write_code(path: str, content: str) -> str:
        """将代码文件写入 builder→tester--src 目录。路径相对于该目录。

        Args:
            path: 代码文件路径（相对于 builder→tester--src/ 目录），如 "main.py"
            content: 代码内容
        """
        clean_path = path.replace("\\", "/").lstrip("/")
        if ".." in clean_path.split("/"):
            return "错误：路径不能包含 '..'（禁止目录逃逸）。"

        base_dir = os.path.join(context_dir, "builder→tester--src")
        full_path = os.path.join(base_dir, clean_path)

        # 验证路径在 base_dir 内
        real_base = os.path.realpath(base_dir)
        real_target = os.path.realpath(os.path.dirname(full_path))
        if not real_target.startswith(real_base):
            return f"错误：禁止写入 {base_dir} 之外的路径。"

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = os.path.getsize(full_path)
        return (
            f"代码已成功写入：{full_path}\n"
            f"文件大小：{file_size} 字节\n"
            f"相对路径：{clean_path}"
        )

    return write_code


@tool
def run_command(command: str) -> str:
    """运行 shell 命令。用于代码检查（语法、格式）、列出文件、查看目录结构。

    仅允许安全命令：
    - python -c <code>        — 执行 Python 代码片段
    - python --version        — 查看 Python 版本
    - pip list                — 查看已安装包
    - ls <path>               — 列出目录内容
    - dir <path>              — Windows 下列出目录内容
    - type <path>             — Windows 下查看文件内容
    - cat <path>              — 查看文件内容

    Args:
        command: 要运行的 shell 命令
    """
    # 安全白名单
    allowed_prefixes = [
        "python -c ",
        "python --version",
        "pip list",
        "ls ",
        "dir ",
        "type ",
        "cat ",
        "pytest ",
        "flake8 ",
        "black --check ",
        "python -m ",
    ]

    if not any(command.startswith(prefix) for prefix in allowed_prefixes):
        return (
            f"错误：不允许的命令 '{command}'。\n"
            f"仅允许：{', '.join(allowed_prefixes[:5])} 等安全命令。"
        )

    try:
        import subprocess
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        if result.stderr:
            stderr = result.stderr.strip()
            if stderr:
                output += "\n\nSTDERR:\n" + stderr[:2000]
        return output if output else "命令执行完成（无输出）"
    except subprocess.TimeoutExpired:
        return "命令执行超时（30 秒）。"
    except Exception as e:
        return f"命令执行失败：{e}"


def _make_query_knowledge():
    """创建 query_knowledge 工具。"""

    @tool
    def query_knowledge(query: str) -> str:
        """查询内部知识库（wiki）。需要了解技术方案时使用。

        Args:
            query: 查询关键词或问题
        """
        from ..knowledge import query_knowledge as _query
        return _query(query)

    return query_knowledge


def _get_system_prompt() -> str:
    """构建 Builder Agent 的系统提示词。"""
    return """你是 Builder — 软件工程师。

## 你的任务
1. 使用 read_file 工具读取 Designer 的需求分析和架构设计
2. 根据设计实现可运行的代码
3. 如果 Tester 提供了修复指令，根据修复指令修改代码
4. 代码放在 `builder→tester--src/` 目录下

## 可用工具
- **read_file(path)**: 读取文件内容（读 Designer 设计文档、Tester 修复指令）
- **write_code(path, content)**: 写入代码文件到 builder→tester--src/ 目录
- **run_command(command)**: 运行 shell 命令（用于语法检查、目录浏览）
- **query_knowledge(query)**: 查询内部知识库

## 工作流程（首次运行）
1. 用 read_file 读取 Designer 的需求分析和架构设计
2. 实现代码：用 write_code 写入每个文件
3. 用 run_command 做语法检查

## 工作流程（回退修复）
1. 用 read_file 读取修复指令（路径会在用户消息中提供）
2. 用 read_file 读取 Designer 设计
3. 根据修复指令修改代码
4. 用 run_command 做语法检查

## 编码规范
- 代码放在 builder→tester--src/ 目录，子目录按功能组织
- 每个文件写完后标注：文件路径 + 功能说明
- 代码要有基本的错误处理
- 使用 Python 3.12+ 语法
"""


def create_builder_agent(
    context_dir: str = "output/default",
    model: str = "deepseek-chat",
):
    """创建 Builder ReAct Agent 实例。

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
        _make_write_code(context_dir),
        run_command,
        _make_query_knowledge(),
    ]

    system_prompt = _get_system_prompt()

    return create_react_agent(llm, tools, prompt=system_prompt)
