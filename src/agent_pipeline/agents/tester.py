"""Tester Agent — QA 工程师 Agent。

对照 Designer 的设计规格，检查 Builder 的代码实现。
通过 → 写测试报告 → 传给 Seller。
失败 → 写修复指令 → 回退到 Builder。

工具：read_file, run_command, write_report
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
    """读取文件内容。用于读取代码文件和设计文档。

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


@tool
def run_command(command: str) -> str:
    """运行 shell 命令。用于检查代码、运行测试。

    仅允许安全命令：
    - python -c <code>        — 执行 Python 检查
    - python --version        — 查看 Python 版本
    - pip list                — 查看已安装包
    - ls <path>               — 列出目录内容
    - dir <path>              — Windows 下列出目录
    - type <path>             — Windows 下查看文件
    - cat <path>              — 查看文件内容
    - pytest <path>           — 运行测试

    Args:
        command: 要运行的 shell 命令
    """
    allowed_prefixes = [
        "python -c ",
        "python --version",
        "python -m ",
        "pip list",
        "ls ",
        "dir ",
        "type ",
        "cat ",
        "pytest ",
    ]

    if not any(command.startswith(prefix) for prefix in allowed_prefixes):
        return (
            f"错误：不允许的命令 '{command}'。\n"
            f"仅允许安全命令。"
        )

    try:
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


def _make_write_report(context_dir: str):
    """创建一个绑定 context_dir 的 write_report 工具。"""

    @tool
    def write_report(path: str, content: str) -> str:
        """将测试报告或修复指令写入文件。路径相对于流水线输出目录。

        测试报告路径示例：tester→seller--测试报告.md
        修复指令路径示例：tester→builder--修复指令.md（当发现代码不符合设计时写入）

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


def _get_system_prompt() -> str:
    """构建 Tester Agent 的系统提示词。"""
    return """你是 Tester — QA 工程师。

## 你的任务
1. 使用 read_file 工具读取 Designer 的设计规格（知道"应该做成什么样"）
2. 使用 read_file 工具读取 Builder 的代码（检查"实际做成了什么样"）
3. 使用 write_report 写入测试报告 `tester→seller--测试报告.md`
4. 如果发现不符合设计的功能，使用 write_report 写入 `tester→builder--修复指令.md`

## 可用工具
- **read_file(path)**: 读取文件内容
- **write_report(path, content)**: 写入测试报告或修复指令
- **run_command(command)**: 运行 shell 命令

## 判定规则
| 判定 | 条件 |
|------|------|
| **Pass** | 所有 Designer 明确列出的功能都有对应实现，代码可运行 |
| **Fail** | 设计里明确的功能缺失、行为不符、运行报错 |
| **不判定** | 设计里没提的功能，代码有没有都不管（沉默即不存在） |

## 测试报告格式（tester→seller--测试报告.md）
```markdown
# 测试报告

## 逐条检查
- [ ] F001 功能名: ✅ 通过 | ❌ 未通过
  - 预期行为：...
  - 实际行为：...
- ...

## 总结
通过: N 项 | 失败: N 项 | 未判定: N 项
```

## 修复指令格式（tester→builder--修复指令.md）
```markdown
# 修复指令

## 不符合项
- **功能**: F001 功能名
  - **预期**: ...
  - **实际**: ...
  - **修复方向**: ...
```

## 工作流程
1. 读取设计文档（需求分析 + 架构设计）
2. 浏览代码目录，读取所有代码文件
3. 逐条对照设计规格检查
4. 写入测试报告
5. 如果有不符合项，写入修复指令
"""


def create_tester_agent(
    context_dir: str = "output/default",
    model: str = "deepseek-chat",
):
    """创建 Tester ReAct Agent 实例。

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
        run_command,
        _make_write_report(context_dir),
    ]

    system_prompt = _get_system_prompt()

    return create_react_agent(llm, tools, prompt=system_prompt)
