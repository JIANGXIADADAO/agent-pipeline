"""Scout Agent -- 市场调研。

从 agents/templates/scout.template.md 深度提取方法论：
- 每个结论标注来源 + 可靠等级
- Designer 不做搜索--所有市场数据来自本 Agent
- 多轮搜索：第一轮扫描、第二轮深挖
- 反模式：无源判断、模糊描述、一次搜索就写报告
"""

import os
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool


# ==== 工具实现 ====

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """搜索互联网获取市场或技术信息。使用 DuckDuckGo HTML（免费免 Key）。"""
    import httpx
    from bs4 import BeautifulSoup

    url = "https://html.duckduckgo.com/html/"
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.post(url, data={"q": query})
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for i, result in enumerate(soup.select(".result, .web-result, article")[:max_results]):
            title_el = result.select_one(".result__title a, .result__a, h2 a, .title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link = title_el.get("href", "")
            if link.startswith("//"):
                link = "https:" + link
            snippet_el = result.select_one(".result__snippet, .snippet, .content, p")
            snippet = snippet_el.get_text(strip=True)[:200] if snippet_el else ""
            results.append(f"[{i+1}] {title}\n    URL: {link}\n    摘要: {snippet}")

        if results:
            return "\n\n".join(results)

        text = soup.get_text()
        lines = [l.strip() for l in text.split("\n") if l.strip() and len(l) > 30]
        return "\n".join(lines[:15]) if lines else f"未找到 '{query}' 的搜索结果。"

    except Exception as e:
        return f"搜索出错: {e}。搜索服务不可用。"


@tool
def read_url(url: str) -> str:
    """读取指定 URL 的文本内容（去除 HTML 标签）。"""
    import httpx
    from bs4 import BeautifulSoup

    if not url.startswith(("http://", "https://")):
        return f"不支持的 URL 协议: {url}"

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}) as client:
            response = client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        content = "\n".join(lines)
        if len(content) > 8000:
            content = content[:8000] + "\n\n... (内容已截断)"
        return content if content else "页面内容为空。"

    except Exception as e:
        return f"读取 {url} 出错: {e}"


def _make_write_report(context_dir: str):
    """创建绑定 context_dir 的 write_report 工具（路径安全）。"""
    @tool
    def write_report(path: str, content: str) -> str:
        """写入报告到流水线产出目录。路径相对于输出目录，禁止目录逃逸。"""
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
        file_size = os.path.getsize(full_path)
        return f"报告已成功写入: {full_path}\n文件大小: {file_size} 字节"
    return write_report


def _make_query_knowledge():
    """创建 query_knowledge 工具。"""
    @tool
    def query_knowledge(query: str) -> str:
        """查询公司内部 wiki 知识库。当需求与已有知识相关时使用。"""
        from ..knowledge import query_knowledge as _query
        return _query(query)
    return query_knowledge


# ==== System Prompt ====

def _get_system_prompt(knowledge_context: str = "") -> str:
    prompt = """你是 Scout -- 市场研究员。回答一个问题：这件事能不能做？市场多大？用户是谁？竞品怎么做的？赛道空白在哪？

## 硬约束
- **每个结论标注来源与可靠等级**：[确认]/[多方印证]/[单一来源]/[待验证]。不写无源判断。
- **Designer 不做搜索**：它的所有市场数据来自你的报告。报告不完整 = Designer 瞎了。
- **多轮搜索**：至少两轮。第一轮扫全景，第二轮深挖具体来源。一次搜索就写报告 = 不合格。

## 反模式（以下行为直接导致产出不合格）
- "根据行业共识..." -- 哪个行业？谁的共识？
- "竞品包括 A、B、C..." -- 每个竞品必须附来源 URL
- "市场很大" -- 必须给具体数字、年份、来源
- 只搜不读 -- search_web 找到 URL 后必须用 read_url 读内容，只看摘要不够
- 假装确定 -- 不确定的标注 [待验证]，不要编

## 可用工具
- **search_web(query, max_results=5)**: 搜索互联网，返回标题+URL+摘要
- **read_url(url)**: 读取网页完整内容（自动去 HTML）
- **write_report(path, content)**: 写入报告
- **query_knowledge(query)**: 查询公司内部 wiki

## 调研流程
1. search_web 搜索 2-3 组不同关键词，覆盖市场/竞品/技术方向
2. 从搜索结果中选出有价值的 URL，用 read_url 逐一深度阅读
3. 用 query_knowledge 查公司 wiki 里是否有相关已有研究
4. 用 write_report 写入结构化报告（路径：`scout->designer--调研报告.md`）

## 报告结构（五章，缺一章即不完整）
```
# 市场调研报告

## 一、市场概述
- 市场规模（具体数字 + 年份 + 来源）
- 增长率（CAGR + 预测期 + 来源）
- 关键驱动力（2-3 条，每条有数据支撑）

## 二、竞品分析
每个竞品：名称 | 一句话定位 | 核心功能 | 定价模式 | 优势 | 劣势 | 来源 URL

## 三、用户画像
- 目标用户群体（谁在用 / 谁想用但用不了）
- 痛点链（表层痛点 → 深层痛点）
- 活跃渠道（在哪讨论、在哪购买）

## 四、赛道空白
- 品牌真空 / 定价真空 / 产品形态真空 / 中文生态真空 / 非开发者真空
- 不是每类都必须有空白，标注"未发现明显空白"也是有效结论

## 五、技术趋势
- 关键技术栈变化
- 新兴方向与信号
- 与公司已有知识的关联（参考 query_knowledge 结果）
```

## 写作规范
- 中文撰写，不少于 1000 字
- 数据必须有出处（[来源名, 年份] 格式）
- 不确定的标注 [待验证]
- 使用 Markdown 表格、列表增强可读性
"""
    if knowledge_context:
        prompt += f"\n## 内部知识参考\n{knowledge_context}\n"
    return prompt


# ==== Agent 创建 ====

def create_scout_agent(context_dir: str = "output/default",
                       knowledge_context: str = "",
                       model: str = "deepseek-chat"):
    """创建 Scout ReAct Agent。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未设置。")

    llm = ChatOpenAI(model=model, api_key=api_key,
                     base_url="https://api.deepseek.com",
                     temperature=0.3, max_retries=0)

    tools = [search_web, read_url,
             _make_write_report(context_dir), _make_query_knowledge()]

    return create_react_agent(llm, tools,
                              prompt=_get_system_prompt(knowledge_context))
