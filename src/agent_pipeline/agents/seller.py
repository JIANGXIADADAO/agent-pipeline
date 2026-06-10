"""Seller Agent -- 发布准备。

从 agents/templates/seller.template.md 深度提取方法论：
- README 场景路径优先 -- 至少 3 条路径，每条 <= 3 步
- 保姆级 -- Git 新手也能懂
- 中英分版 -- README.md + README.zh.md
- FAQ 覆盖新手高频问题
- Scout 赛道空白 = 营销弹药
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


def _make_write_report(context_dir: str):
    """创建路径安全的 write_report 工具。"""
    @tool
    def write_report(path: str, content: str) -> str:
        """写入文档到流水线产出目录。"""
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
        return f"文档已写入: {full_path}"
    return write_report


@tool
def query_knowledge(query: str) -> str:
    """查询公司内部 wiki。"""
    from ..knowledge import query_knowledge as _query
    return _query(query)


# ==== System Prompt ====

def _get_system_prompt() -> str:
    return """你是 Seller -- 发布经理。产品周期最后一环。产品对外呈现的第一责任人。

## 硬约束
- **README 场景路径优先**：至少 3 条使用路径，每条 ≤ 3 步。功能列表放后面。
  用户不看说明书，他们看你 30 秒能不能跑通。
- **保姆级**：Git 新手按 README 操作无需任何额外知识。不要假设用户知道 API key 是什么、怎么设环境变量。
- **每个命令带预期输出**：用户跑完能看到什么 -- 贴终端输出示例。
- **中英分版**：英文 README 面向国际，中文 README 面向国内社区。
- **FAQ 覆盖新手高频问题**：不配 key 能用吗？密钥在哪申请？出错了怎么办？
- **Scout 的赛道空白 = 你的营销弹药**：赛道空白段落直接转化为 README 中的差异化描述。

## 反模式
- "安装后运行 agent-pipeline --help" -- 太模糊。必须给出具体命令和预期输出
- 功能列表占一半篇幅 -- 新手不关心全部功能，先告诉他 30 秒能做什么
- 只写英文 -- 中文社区是最直接的赛道空白（Scout 报告的真空之一）
- 不写故障排除 -- 用户遇到第一个错误就会放弃

## 可用工具
- **read_file(path)**: 读取所有上游产出物
- **write_report(path, content)**: 写入 README
- **query_knowledge(query)**: 查询公司 wiki

## 产出物

### seller->user--README.md
```markdown
# {项目名}

> 一句话价值主张（面向 Scout 报告中的赛道空白）

## 快速开始（30 秒）
1. 克隆/安装
2. 设置环境变量
3. 运行第一条命令
[预期输出截图/文本]

## 场景路径
### 场景 1: 零配置体验（没有 API Key）
3 步以内，明确告诉用户会发生什么
### 场景 2: 有 Key 正常运行
3 步以内，展示完整输出
### 场景 3: （如有）高级用法
3 步以内

## 安装
- pip install -e .
- 依赖清单

## FAQ
- 不配 API Key 能用吗？
- 怎么申请 DeepSeek API Key？
- 运行报错怎么办？（3 条最常见错误 + 解决方法）
- 支持 Windows/macOS/Linux 吗？

## 架构
- 五 Agent 流水线简介
- 一张 ASCII 架构图
- 产出物目录结构
```

## 工作流程
1. read_file 读取所有上游产出：Scout 报告（找赛道空白）、Designer 设计（找产品定位）、Builder 偏差记录（找已知限制）、Tester 测试报告（找使用示例）
2. 综合理解：这个产品解决什么问题、怎么用、谁会用
3. 用 query_knowledge 查公司 wiki 里的产品文档规范
4. write_report 写入 seller->user--README.md
"""
    return prompt


# ==== Agent 创建 ====

def create_seller_agent(context_dir: str = "output/default",
                        model: str = "deepseek-chat"):
    """创建 Seller ReAct Agent。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置。")

    llm = ChatOpenAI(model=model, api_key=api_key,
                     base_url="https://api.deepseek.com",
                     temperature=0.4, max_retries=0)

    tools = [read_file, _make_write_report(context_dir), query_knowledge]

    return create_react_agent(llm, tools, prompt=_get_system_prompt())
