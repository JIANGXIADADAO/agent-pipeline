"""预索引门控 RAG — Phase 1：index.md 关键词子串匹配。

匹配逻辑：
1. 读取 wiki/index.md，提取所有条目（包含 [[...]] 的行）
2. 将需求文本拆分为标记词（中英文）
3. 对每个条目，检查是否有标记词匹配其描述
4. 命中 → 加载对应 wiki 页面内容作为知识上下文
5. 未命中 → 返回空知识
"""

import os
import re
from pathlib import Path
from typing import Optional

from .models import PipelineState

# Wiki 根目录（相对于项目根目录），可通过环境变量覆盖
DEFAULT_WIKI_PATH = "../../wiki"


def _get_wiki_root() -> Path:
    """获取 wiki 根目录。"""
    env_path = os.environ.get("AGENT_PIPELINE_WIKI_PATH")
    if env_path:
        return Path(env_path)
    return Path(DEFAULT_WIKI_PATH)


def _read_index_entries() -> list[tuple[str, str, str]]:
    """读取 index.md，返回 [(page_type, page_name, description), ...]。

    page_type: "entities" | "concepts" | "sources" | "comparisons" | "queries"
    page_name: 页面名（如 "codegraph"）
    description: 页面描述
    """
    wiki_root = _get_wiki_root()
    index_path = wiki_root / "index.md"
    if not index_path.exists():
        return []

    content = index_path.read_text(encoding="utf-8")
    entries = []

    # 匹配格式: "- [[{type}/{name}]] — {description}"
    # 也匹配: "- [[{name}|{alias}]]" 或 "- [[{type}/{name}|{alias}]]"
    pattern = re.compile(
        r"-\s+\[\["                    # 列表项开始的 [[
        r"(?:(entities|concepts|sources|comparisons|queries|agents/templates)/)?"  # 可选类型前缀
        r"([^\]|]+)"                   # 页面名
        r"(?:\|[^\]]+)?"              # 可选别名
        r"\]\]"                        # 结束 ]]
        r"\s*(?:[—–-]\s*(.+))?"       # 可选描述（—或-分隔）
    )

    for line in content.split("\n"):
        line = line.strip()
        m = pattern.match(line)
        if m:
            page_type = m.group(1) or "unknown"
            page_name = m.group(2).strip()
            description = (m.group(3) or "").strip()
            entries.append((page_type, page_name, description))

    return entries


def _extract_keywords(text: str) -> list[str]:
    """从文本中提取有意义的标记词。"""
    # 去除标点符号，按空白分割
    cleaned = re.sub(r"[^\w\s一-鿿]", " ", text)
    words = cleaned.split()

    # 过滤：至少 2 个字符，且不是纯数字
    keywords = []
    for w in words:
        w = w.strip()
        if len(w) >= 2 and not w.isdigit():
            keywords.append(w.lower())
    return keywords


def _match_requirement(requirement: str, entries: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """将需求与 index.md 条目匹配，返回命中的条目列表。"""
    keywords = _extract_keywords(requirement)
    if not keywords:
        return []

    matches = []
    for page_type, page_name, description in entries:
        # 在描述中检查关键词匹配
        desc_lower = description.lower()
        name_lower = page_name.lower()

        matched_kw = []
        for kw in keywords:
            if kw in desc_lower or kw in name_lower:
                matched_kw.append(kw)

        if matched_kw:
            matches.append((page_type, page_name, description))

    return matches


def _load_wiki_page(page_type: str, page_name: str) -> Optional[str]:
    """加载对应的 wiki 页面内容。"""
    wiki_root = _get_wiki_root()
    if page_type == "unknown":
        page_path = wiki_root / f"{page_name}.md"
    elif page_type == "agents/templates":
        # Agent 模板在项目内的 agents/templates/ 目录
        from pathlib import Path
        page_path = Path.cwd() / ".." / ".." / "agents" / "templates" / f"{page_name}.md"
    else:
        page_path = wiki_root / page_type / f"{page_name}.md"

    if page_path.exists():
        content = page_path.read_text(encoding="utf-8")
        # 截取前 2000 字符作为上下文，避免过长
        return content[:2000]
    return None


def match_index_knowledge(state: PipelineState) -> PipelineState:
    """预索引门控 RAG：匹配 index.md，更新 state 的 knowledge_* 字段。

    这是 Orchestrator 调用的主函数。
    """
    entries = _read_index_entries()
    if not entries:
        state.knowledge_hit = False
        state.knowledge_sources = []
        return state

    matches = _match_requirement(state.requirement, entries)

    if matches:
        state.knowledge_hit = True
        state.knowledge_sources = [f"{t}/{n}" for t, n, _ in matches]
    else:
        state.knowledge_hit = False
        state.knowledge_sources = []

    return state


def build_knowledge_context(state: PipelineState) -> str:
    """根据命中的知识源，构建 Agent 可读的知识上下文文本。"""
    if not state.knowledge_hit or not state.knowledge_sources:
        return "knowledge_source: none"

    wiki_root = _get_wiki_root()
    sections = ["## 内部知识上下文\n"]

    for source_ref in state.knowledge_sources:
        # source_ref 格式如 "entities/codegraph" 或 "concepts/AI Agent 设计模式"
        parts = source_ref.split("/", 1)
        if len(parts) == 2:
            page_type, page_name = parts
        else:
            page_type, page_name = "unknown", parts[0]

        content = _load_wiki_page(page_type, page_name)
        if content:
            sections.append(f"### {page_name}\n\n来源: {source_ref}\n\n{content}\n")

    if len(sections) == 1:
        return "knowledge_source: none"

    return "\n".join(sections)


def query_knowledge(query: str) -> str:
    """Agent 工具函数：在运行时查询预索引知识库。

    此函数被注册为 Scout Agent 的 query_knowledge 工具。
    返回匹配的 wiki 知识文本，或 "knowledge_source: none"。
    """
    entries = _read_index_entries()
    if not entries:
        return "knowledge_source: none"

    matches = _match_requirement(query, entries)
    if not matches:
        return "knowledge_source: none"

    wiki_root = _get_wiki_root()
    sections = []

    for page_type, page_name, description in matches:
        content = _load_wiki_page(page_type, page_name)
        if content:
            sections.append(f"---\n### {page_name}\n{description}\n\n{content}")

    if not sections:
        return "knowledge_source: none"

    return "\n".join(sections)
