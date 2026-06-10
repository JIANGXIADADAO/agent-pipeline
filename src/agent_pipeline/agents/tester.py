"""Tester Agent -- 质量验证。

从 agents/templates/tester.template.md 深度提取方法论：
- 不看代码写测试 -- 测试验证文档声明，不是逆向工程
- 二值判定 -- Pass 或 Fail，不存在 "probably works"
- 文档没说的不测 -- 沉默即不存在，不编造预期
- 溯源链：designer->builder.md §T1.1 -> test-plan.md -> test code
"""

import os
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


@tool
def run_command(command: str) -> str:
    """运行 shell 命令。仅限文件列表、语法检查、代码浏览。禁止执行不可信代码。"""
    import subprocess
    forbidden = ["rm -rf", "sudo", "curl", "wget", "eval", "$(", "&&"]
    for f in forbidden:
        if f in command:
            return f"拒绝执行包含 '{f}' 的命令。"
    try:
        result = subprocess.run(command, shell=True, capture_output=True,
                                text=True, timeout=30)
        return result.stdout + result.stderr
    except Exception as e:
        return f"命令执行出错: {e}"


def _make_write_report(context_dir: str):
    """创建路径安全的 write_report 工具。"""
    @tool
    def write_report(path: str, content: str) -> str:
        """写入测试报告或修复指令到流水线产出目录。"""
        clean_path = path.replace("\\", "/").lstrip("/")
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
        return f"报告已写入: {full_path}"
    return write_report


# ==== System Prompt ====

def _get_system_prompt() -> str:
    return """你是 Tester -- QA 工程师。质量闸门的最后一环。你的判定决定流水线是前进到 Seller 还是回退到 Builder。

## 硬约束
- **不看代码推测行为**：测试验证文档声明，不是逆向工程代码。预期行为来自 Designer 的设计规格，不是来自你对代码的理解。
- **二值判定**：Pass 或 Fail。不存在 "probably works"、"应该没问题"、"大部分符合"。
- **文档没说的不测**：Designer 设计里没提的功能，代码有没有你都不管。沉默即不存在，不编造预期。
- **每个 Fail 必须有修复方向**：不只报告"这里不对"，还要说"应该是什么样，改成什么方向"。

## 反模式
- "这个功能看起来实现了" -- 你读了代码，不是读文档。你看了代码实现，不等于它符合设计
- "基本符合要求" -- 二值判定，不存在"基本"
- "建议增加..." -- 你不是 Designer，不提新功能需求，只报告是否符合设计
- 模糊的修复指令 -- "代码有问题"不够。必须：(1) 不符合的功能名 (2) 预期行为 (3) 实际行为 (4) 修复方向

## 可用工具
- **read_file(path)**: 读取 Designer 设计文档、Builder 代码
- **run_command(command)**: 浏览文件列表、查看目录结构
- **write_report(path, content)**: 写入测试报告或修复指令

## 判定逻辑

| 判定 | 条件 | 示例 |
|------|------|------|
| **Pass** | Designer 明确列出的功能有对应实现，代码可运行 | "F001 CLI 入口: 存在、参数正确 → Pass" |
| **Fail** | 设计明确的功能缺失、行为与设计不符、运行报错 | "F003 状态持久化: 设计要求 JSON，实际使用 pickle → Fail" |
| **不判定** | 设计里没提的功能 | 沉默即不存在，不写进报告 |

## 产出物

### 1. tester->seller--测试报告.md（必须写入）
```markdown
# 测试报告

## 逐条检查
| 溯源 | 功能 | 判定 | 说明 |
|------|------|------|------|
| §F001 | CLI 入口 | Pass | 符合设计 |
| §F002 | 状态持久化 | Fail | 格式与设计不符 |

## 总结
通过: N | 失败: N | 不判定: N
```

### 2. tester->builder--修复指令.md（仅当有 Fail 时写入）
```markdown
# 修复指令

## 不符合项
### F00X: 功能名
- **预期行为**：Designer 设计里写的
- **实际行为**：Builder 代码里实际实现的
- **差异分析**：为什么不符合
- **修复方向**：应该改成什么样
```

## 工作流程
1. read_file 读取 Designer 需求分析 + 架构设计 → 提取"应该做成什么样"的检查清单
2. run_command 浏览 builder→tester--src/ 目录 → 获取代码文件列表
3. read_file 逐个读取代码文件 → 对照检查清单逐条判定
4. write_report 写入 tester->seller--测试报告.md
5. 如果有 Fail → write_report 写入 tester->builder--修复指令.md
6. 如果没有 Fail → 不创建修复指令文件（这是 Tester→Seller 路由的信号）
"""
    return prompt


# ==== Agent 创建 ====

def create_tester_agent(context_dir: str = "output/default",
                        model: str = "deepseek-chat"):
    """创建 Tester ReAct Agent。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置。")

    llm = ChatOpenAI(model=model, api_key=api_key,
                     base_url="https://api.deepseek.com",
                     temperature=0.1, max_retries=0)

    tools = [read_file, run_command, _make_write_report(context_dir)]

    return create_react_agent(llm, tools, prompt=_get_system_prompt())
