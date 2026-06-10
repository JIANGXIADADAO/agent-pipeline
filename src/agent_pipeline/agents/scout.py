"""Scout Agent — 市场调研 Agent。

使用 langgraph.prebuilt.create_react_agent 创建 ReAct Agent，
绑定 4 个工具：search_web, read_url, write_report, query_knowledge。
"""

import os
import re
from pathlib import Path
from typing import Optional

from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool


# ---- 工具实现 ----

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """搜索互联网获取市场或技术信息。返回搜索结果列表，包含标题、URL 和摘要。

    Args:
        query: 搜索关键词
        max_results: 最大结果数 (默认 5)
    """
    import httpx
    from urllib.parse import urlencode

    # 使用 DuckDuckGo HTML 搜索（无需 API Key）
    url = "https://html.duckduckgo.com/html/"
    data = {"q": query}

    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.post(url, data=data)
            response.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        # DuckDuckGo HTML 搜索结果在 .result 或 .web-result 容器中
        for i, result in enumerate(
            soup.select(".result, .web-result, article")[:max_results]
        ):
            # 提取标题
            title_el = result.select_one(
                ".result__title a, .result__a, h2 a, .title a"
            )
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")

            # DuckDuckGo 的链接是重定向 URL，需要解析
            if link.startswith("//"):
                link = "https:" + link

            # 提取摘要
            snippet_el = result.select_one(
                ".result__snippet, .snippet, .content, p"
            )
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            results.append(f"[{i+1}] {title}\n    URL: {link}\n    摘要: {snippet[:200]}")

        if results:
            return "\n\n".join(results)

        # 降级：尝试从纯文本提取
        text = soup.get_text()
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # 返回前 20 行有意义的文本
        meaningful = [l for l in lines if len(l) > 30 and not l.startswith(("(", "[", "<"))]
        if meaningful:
            return "\n".join(meaningful[:15])

        return f"未找到 '{query}' 的搜索结果。"

    except httpx.TimeoutException:
        return "搜索服务超时（15 秒），请稍后重试。"
    except httpx.HTTPStatusError as e:
        return f"搜索服务暂时不可用 (HTTP {e.response.status_code})，请稍后重试。"
    except Exception as e:
        return f"搜索出错: {e}。搜索服务不可用，请使用已有知识回答。"


@tool
def read_url(url: str) -> str:
    """读取指定 URL 的文本内容。返回网页的纯净文本（去除 HTML 标签）。

    Args:
        url: 要读取的完整 URL
    """
    import httpx
    from bs4 import BeautifulSoup

    # 安全检查：只允许 http/https
    if not url.startswith(("http://", "https://")):
        return f"不支持的 URL 协议: {url}。仅支持 http:// 和 https://。"

    try:
        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        ) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # 移除脚本和样式
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        # 清理空行
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        content = "\n".join(lines)

        # 限制长度，避免超长内容
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (内容已截断，全文过长)"

        return content if content else "页面内容为空。"

    except httpx.TimeoutException:
        return f"读取 {url} 超时（30 秒）。"
    except httpx.HTTPStatusError as e:
        return f"读取 {url} 失败: HTTP {e.response.status_code}"
    except Exception as e:
        return f"读取 {url} 出错: {e}"


def _make_write_report(context_dir: str):
    """创建一个绑定 context_dir 的 write_report 工具。

    Args:
        context_dir: 允许写入的目录路径（安全边界）
    """

    @tool
    def write_report(path: str, content: str) -> str:
        """将调研报告写入文件。路径相对于流水线输出目录，禁止写入其他位置。

        Args:
            path: 文件路径（相对于流水线输出目录），例如 "scout/report.md"
            content: 文件内容
        """
        # 安全校验：防止路径逃逸
        clean_path = path.replace("\\", "/").lstrip("/")
        if ".." in clean_path.split("/"):
            return "错误：路径不能包含 '..'（禁止目录逃逸）。"

        full_path = os.path.join(context_dir, clean_path)
        # 验证路径在 context_dir 内
        real_context = os.path.realpath(context_dir)
        real_target = os.path.realpath(os.path.dirname(full_path))

        if not real_target.startswith(real_context):
            return f"错误：禁止写入 {context_dir} 之外的路径。"

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        file_size = os.path.getsize(full_path)
        return (
            f"报告已成功写入: {full_path}\n"
            f"文件大小: {file_size} 字节\n"
            f"相对路径: {clean_path}"
        )

    return write_report


def _make_query_knowledge():
    """创建 query_knowledge 工具，使用已有的 knowledge 模块。"""

    @tool
    def query_knowledge(query: str) -> str:
        """查询内部知识库（wiki）。当用户需求涉及项目中已有知识时使用。

        Args:
            query: 查询关键词或问题
        """
        # 延迟导入以避免循环依赖
        from ..knowledge import query_knowledge as _query

        return _query(query)

    return query_knowledge


def _get_system_prompt(knowledge_context: str = "") -> str:
    """构建 Scout Agent 的系统提示词。"""
    prompt = """你是 Scout — 市场研究员。
你的任务是根据用户需求进行市场调研，输出结构化调研报告。

## 可用工具
- **search_web(query, max_results)**: 搜索互联网。用于查找市场数据、竞品信息、技术趋势。
- **read_url(url)**: 读取网页的完整内容。用于深度分析搜索结果中的具体页面。
- **write_report(path, content)**: 将调研报告写入文件。路径相对于输出目录，如 "scout→designer--调研报告.md"。
- **query_knowledge(query)**: 查询内部知识库。当需求与已有知识相关时使用。

## 调研流程
1. 先用 search_web 搜索市场概况
2. 用 read_url 深入阅读有价值的来源
3. 必要时用 query_knowledge 查询内部知识
4. 最后用 write_report 输出完整的调研报告

## 调研报告要求
报告必须包含以下章节（Markdown 格式）：
- 市场概述：市场规模、增长率、主要趋势
- 竞品分析：主要参与者、产品特点、市场份额
- 用户画像：目标用户、痛点、需求
- 赛道空白：未被满足的需求、创新机会
- 技术趋势：关键技术发展、技术栈变化

## 输出路径
- 使用 write_report 工具将调研报告写入 `scout→designer--调研报告.md`
- 路径参数传递 `scout→designer--调研报告.md`（相对于输出目录）

## 写作规范
- 使用中文撰写报告
- 每个观点附带数据或来源引用
- 报告长度不少于 1000 字
- 使用 Markdown 格式（标题、列表、表格等）
"""
    if knowledge_context:
        prompt += f"\n## 内部知识参考\n{knowledge_context}\n"

    return prompt


def create_scout_agent(
    context_dir: str = "output/default",
    knowledge_context: str = "",
    model: str = "deepseek-chat",
):
    """创建 Scout ReAct Agent 实例。

    Args:
        context_dir: 流水线上下文目录（用于 write_report 的路径隔离）
        knowledge_context: 预索引 RAG 的知识上下文文本
        model: DeepSeek 模型名称（deepseek-chat 或 deepseek-reasoner）
    """
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError(
            "DEEPSEEK_API_KEY 未设置。设置: export DEEPSEEK_API_KEY=sk-xxx"
        )

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://api.deepseek.com",
        temperature=0.3,
        max_retries=0,  # 我们自己管理重试
    )

    tools = [
        search_web,
        read_url,
        _make_write_report(context_dir),
        _make_query_knowledge(),
    ]

    system_prompt = _get_system_prompt(knowledge_context)

    return create_react_agent(
        llm,
        tools,
        prompt=system_prompt,
    )
