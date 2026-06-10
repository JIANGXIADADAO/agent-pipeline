"""Builder Agent -- 编码实现。

从 agents/templates/builder.template.md 深度提取方法论：
- 操作前先解释 -- 是什么、干什么用、为什么
- 实现偏差必须记录 -- 与 designer brief 不同 → builder->tester.md
- src/tests/ 只读 -- Tester 的领地
- 代码是 Builder 和 Tester 之间的交接物
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


def _make_write_code(context_dir: str):
    """创建路径安全的 write_code 工具。代码只能写入 builder→tester--src/。"""
    @tool
    def write_code(path: str, content: str) -> str:
        """写入代码文件到 builder→tester--src/ 目录。路径相对于该目录。"""
        clean_path = path.replace("\\", "/").lstrip("/")
        if ".." in clean_path.split("/"):
            return "错误：路径不能包含 '..'。"
        src_dir = os.path.join(context_dir, "builder→tester--src")
        full_path = os.path.join(src_dir, clean_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"代码已写入: {full_path}"
    return write_code


@tool
def run_command(command: str) -> str:
    """运行 shell 命令。仅限语法检查、文件列表、依赖安装。禁止执行不可信代码。"""
    import subprocess
    forbidden = ["rm -rf", "sudo", "curl", "wget", "eval", "$(", "&&"]
    for f in forbidden:
        if f in command:
            return f"拒绝执行包含 '{f}' 的命令。"
    try:
        result = subprocess.run(command, shell=True, capture_output=True,
                                text=True, timeout=30, cwd=os.getcwd())
        return result.stdout + result.stderr
    except Exception as e:
        return f"命令执行出错: {e}"


@tool
def query_knowledge(query: str) -> str:
    """查询公司内部 wiki 知识库。"""
    from ..knowledge import query_knowledge as _query
    return _query(query)


# ==== System Prompt ====

def _get_system_prompt() -> str:
    return """你是 Builder -- 软件工程师。负责编码、调试。代码是你和 Tester 之间的交接物，不是私有领地。

## 硬约束
- **操作前先解释**：做什么、干什么用、为什么这样实现。先解释再写代码。
- **实现偏差必须记录**：与 Designer 设计不同的技术决策 → 写入 builder->tester--偏差记录.md
- **src/tests/ 只读**：测试是 Tester 的独家领地。能读能跑，不能改。
- **Tester 不读你的大脑**：他们读 Designer 设计 + 你的代码 + 你的偏差记录。代码写不清楚 = Tester 测不准。

## 反模式
- 直接写代码不解释 -- 每个文件先说明用途和设计依据
- 静默偏离设计 -- 任何偏差必须显式记录，Tester 需要知道
- 过度工程化 -- 先满足 P0，再考虑扩展性。Ship working code first
- 跳过语法检查 -- 写完代码后必须用 run_command 验证语法
- 硬编码路径 -- 使用相对路径和 context_dir

## 可用工具
- **read_file(path)**: 读取 Designer 设计文档、Tester 修复指令
- **write_code(path, content)**: 写入代码文件到 builder→tester--src/
- **run_command(command)**: 运行语法检查/文件列表（受安全限制）
- **query_knowledge(query)**: 查询公司内部 wiki

## 两种工作模式

### 首次运行（正常流程）
1. read_file 读取 Designer 需求分析 + 架构设计
2. 理解设计意图 -- 不是"照着 API 写"，是"照着设计意图写"
3. 逐文件 write_code -- 先解释功能，再写代码
4. run_command 做语法/类型检查
5. write_code 写入 builder->tester--偏差记录.md（如果有偏差）

### 回退修复（Tester 发现问题）
1. read_file 读取 tester->builder--修复指令.md
2. read_file 重新读取 Designer 设计 -- 对照修复指令理解问题
3. 根据修复指令改代码 -- 修具体问题，不做无关重构
4. run_command 验证修复
5. 更新 builder->tester--偏差记录.md

## 编码规范
- 代码放入 builder→tester--src/，按功能组织子目录
- Python 3.12+ 语法
- 基本错误处理 -- 不假设一切正常
- 每个文件顶部注释：功能说明 + 对应设计中的哪个模块
"""
    return prompt


# ==== Agent 创建 ====

def create_builder_agent(context_dir: str = "output/default",
                         model: str = "deepseek-chat"):
    """创建 Builder ReAct Agent。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置。")

    llm = ChatOpenAI(model=model, api_key=api_key,
                     base_url="https://api.deepseek.com",
                     temperature=0.3, max_retries=0)

    tools = [read_file, _make_write_code(context_dir),
             run_command, query_knowledge]

    return create_react_agent(llm, tools, prompt=_get_system_prompt())
