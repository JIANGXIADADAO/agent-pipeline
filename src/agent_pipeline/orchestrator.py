"""Orchestrator — Phase 2 LangGraph StateGraph 流水线编排器。

从 Phase 1 的 Python 函数直线流程升级为七节点 LangGraph StateGraph：

节点:
  1. parse        — 解析需求 + 预索引门控 RAG
  2. scout        — Scout Agent 市场调研
  3. designer     — Designer Agent 产品设计
  4. builder      — Builder Agent 编码实现
  5. tester       — Tester Agent 质量验证（含条件回退）
  6. seller       — Seller Agent 发布准备
  7. finalize     — 收尾 + 状态持久化

条件边:
  tester → builder（回退，最多 3 次）
  tester → seller（通过）
"""

import os
import re
import time
import uuid
import operator
from datetime import datetime, timezone
from typing import TypedDict, Annotated, Optional, Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .models import PipelineState, AgentOutput
from .state import save_state
from .knowledge import match_index_knowledge, build_knowledge_context


# ============================================================
# 状态类型定义
# ============================================================

class AgentOutputDict(TypedDict, total=False):
    """单个 Agent 的输出（与 models.AgentOutput 对应）。"""
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    output_path: Optional[str]
    summary: str
    raw_output: str
    error: Optional[str]
    retry_count: int
    artifacts: list[str]


class PipelineStateDict(TypedDict, total=False):
    """流水线状态（LangGraph TypedDict 版本）。

    warnings 和 errors 使用 operator.add reducer 实现追加而非覆盖。
    """
    requirement: str
    project_name: str
    project_slug: str
    current_agent: str
    agent_outputs: dict[str, AgentOutputDict]
    status: str                # idle | running | completed | failed
    errors: Annotated[list[str], operator.add]
    warnings: Annotated[list[str], operator.add]
    context_dir: str
    knowledge_hit: bool
    knowledge_sources: list[str]
    knowledge_context: str
    pipeline_id: str
    created_at: str
    updated_at: str
    iteration_count: int       # Builder-Tester 回退轮次计数


# ============================================================
# 工具函数
# ============================================================

def extract_project_name(requirement: str) -> str:
    """从需求文本中提取项目名称。"""
    cleaned = re.sub(
        r"^(请|帮我|麻烦|我要|我想)(调研|分析|研究|开发|设计|实现|做一个|写一个|开发一个|设计一个|研究一下|分析一下|调研一下)",
        "",
        requirement,
    )
    name = cleaned.strip()[:40].strip()
    if not name:
        name = requirement.strip()[:40].strip()
    return name


def slugify(name: str) -> str:
    """将名称转换为文件系统友好的 slug。"""
    slug = re.sub(r"\s+", "-", name.strip())
    slug = re.sub(r"[^\w\-一-鿿]", "", slug)
    slug = slug.lower()
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")
    return slug


# ============================================================
# 工具函数：Agent 调用
# ============================================================

def _invoke_agent(agent, user_message: str, timeout_seconds: int = 300):
    """调用 ReAct Agent 并返回结果消息。"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

    with ThreadPoolExecutor() as executor:
        future = executor.submit(
            agent.invoke,
            {"messages": [{"role": "user", "content": user_message}]},
        )
        try:
            result = future.result(timeout=timeout_seconds)
        except FutureTimeoutError:
            raise TimeoutError(
                f"Agent 执行超时（{timeout_seconds} 秒），已自动终止。"
            )

    messages = result.get("messages", [])
    final_message = messages[-1] if messages else None
    raw_content = ""
    if final_message and hasattr(final_message, "content"):
        raw_content = final_message.content
    elif final_message and isinstance(final_message, dict):
        raw_content = final_message.get("content", "")
    return raw_content


# ============================================================
# 节点函数
# ============================================================

def parse_node(state: PipelineStateDict) -> dict:
    """解析需求 + 预索引门控 RAG。"""
    now = datetime.now(timezone.utc)
    requirement = state.get("requirement", "")

    project_name = extract_project_name(requirement)
    project_slug = slugify(project_name)
    context_dir = f"output/{project_slug}"

    os.makedirs(context_dir, exist_ok=True)

    # 写入原始需求
    req_path = os.path.join(context_dir, "requirement.txt")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write(requirement)

    # 预索引门控 RAG
    ps = PipelineState(requirement=requirement)
    ps = match_index_knowledge(ps)
    knowledge_context = build_knowledge_context(ps)

    updates = {
        "pipeline_id": f"pl_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "project_name": project_name,
        "project_slug": project_slug,
        "context_dir": context_dir,
        "current_agent": "parse",
        "status": "running",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "knowledge_hit": ps.knowledge_hit,
        "knowledge_sources": ps.knowledge_sources,
        "knowledge_context": knowledge_context,
        "agent_outputs": {},
        "errors": [],
        "warnings": [],
        "iteration_count": 0,
    }

    if ps.knowledge_hit:
        updates["warnings"] = [
            f"知识库命中 {len(ps.knowledge_sources)} 条：{', '.join(ps.knowledge_sources)}"
        ]

    save_state(_dict_to_pipeline_state({**state, **updates}))
    return updates


def scout_node(state: PipelineStateDict) -> dict:
    """Scout Agent — 市场调研。"""
    now = datetime.now(timezone.utc)
    context_dir = state["context_dir"]

    from .agents.scout import create_scout_agent

    scout_report_path = os.path.join(context_dir, "scout→designer--调研报告.md")

    entry = {
        "status": "running",
        "started_at": now.isoformat(),
        "retry_count": 0,
        "output_path": scout_report_path,
        "summary": "",
        "raw_output": "",
        "error": None,
        "artifacts": [],
        "completed_at": None,
    }

    outputs = dict(state.get("agent_outputs", {}))
    outputs["scout"] = entry
    save_state(_dict_to_pipeline_state({**state, "agent_outputs": outputs}))

    try:
        agent = create_scout_agent(
            context_dir=context_dir,
            knowledge_context=state.get("knowledge_context", ""),
        )

        user_message = (
            f"需求：{state['requirement']}\n\n"
            f"请进行市场调研，输出报告到 `scout→designer--调研报告.md`。\n"
            f"注意：使用 write_report 工具时，路径参数请写 `scout→designer--调研报告.md`。\n"
            f"报告必须包含：市场概述、竞品分析、用户画像、赛道空白、技术趋势。"
        )

        raw_content = _invoke_agent(agent, user_message)

        # 检查报告是否已由 write_report 写入
        if not os.path.exists(scout_report_path):
            os.makedirs(os.path.dirname(scout_report_path), exist_ok=True)
            with open(scout_report_path, "w", encoding="utf-8") as f:
                f.write(raw_content)

        file_size = os.path.getsize(scout_report_path) if os.path.exists(scout_report_path) else 0
        entry["status"] = "completed"
        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        entry["summary"] = "调研报告已生成"
        entry["raw_output"] = raw_content
        entry["artifacts"] = [scout_report_path]

        if not raw_content and file_size == 0:
            raise ValueError("Scout Agent 返回空结果。")

    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = str(e)

    outputs["scout"] = entry
    return {"agent_outputs": outputs, "current_agent": "scout"}


def designer_node(state: PipelineStateDict) -> dict:
    """Designer Agent — 需求分析 + 架构设计。"""
    now = datetime.now(timezone.utc)
    context_dir = state["context_dir"]

    from .agents.designer import create_designer_agent

    scout_report_path = state.get("agent_outputs", {}).get("scout", {}).get("output_path", "")
    req_path = os.path.join(context_dir, "designer→builder--需求分析.md")
    arch_path = os.path.join(context_dir, "designer→builder--架构设计.md")

    entry = {
        "status": "running",
        "started_at": now.isoformat(),
        "retry_count": 0,
        "output_path": req_path,
        "summary": "",
        "raw_output": "",
        "error": None,
        "artifacts": [req_path, arch_path],
        "completed_at": None,
    }

    outputs = dict(state.get("agent_outputs", {}))
    outputs["designer"] = entry
    save_state(_dict_to_pipeline_state({**state, "agent_outputs": outputs}))

    try:
        agent = create_designer_agent(context_dir=context_dir)

        # 读取 Scout 报告内容
        scout_content = ""
        if scout_report_path and os.path.exists(scout_report_path):
            with open(scout_report_path, "r", encoding="utf-8") as f:
                scout_content = f.read()[:4000]

        user_message = (
            f"需求：{state['requirement']}\n\n"
            f"Scout 调研报告路径：{scout_report_path}\n"
            f"Scout 调研报告摘要（前 4000 字符）：\n\n{scout_content}\n\n"
            f"请基于 Scout 报告完成以下任务：\n"
            f"1. 使用 write_report 工具写入 `designer→builder--需求分析.md`（JTBD + RICE + MVP）\n"
            f"2. 使用 write_report 工具写入 `designer→builder--架构设计.md`（信息架构 + 技术选型 + 数据流）\n"
            f"3. 报告不少于 800 字，全部基于 Scout 报告数据。"
        )

        raw_content = _invoke_agent(agent, user_message)

        entry["status"] = "completed"
        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        entry["summary"] = "需求分析与架构设计已生成"
        entry["raw_output"] = raw_content

        # 确保文件存在
        for path in [req_path, arch_path]:
            if not os.path.exists(path) and raw_content:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"# {os.path.basename(path).replace('.md', '')}\n\n{raw_content[:2000]}")

    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = str(e)

    outputs["designer"] = entry
    return {"agent_outputs": outputs, "current_agent": "designer"}


def builder_node(state: PipelineStateDict) -> dict:
    """Builder Agent — 代码实现。"""
    now = datetime.now(timezone.utc)
    context_dir = state["context_dir"]

    from .agents.builder import create_builder_agent

    iteration = state.get("iteration_count", 0)
    designer_output = state.get("agent_outputs", {}).get("designer", {})
    tester_output = state.get("agent_outputs", {}).get("tester", {})

    src_dir = os.path.join(context_dir, "builder→tester--src")
    fix_prompt_path = os.path.join(context_dir, "tester→builder--修复指令.md")

    entry = {
        "status": "running",
        "started_at": now.isoformat(),
        "retry_count": iteration,
        "output_path": src_dir,
        "summary": "",
        "raw_output": "",
        "error": None,
        "artifacts": [src_dir],
        "completed_at": None,
    }

    outputs = dict(state.get("agent_outputs", {}))
    outputs["builder"] = entry
    save_state(_dict_to_pipeline_state({**state, "agent_outputs": outputs}))

    try:
        agent = create_builder_agent(context_dir=context_dir)

        # 读取上游设计文档
        req_path = os.path.join(context_dir, "designer→builder--需求分析.md")
        arch_path = os.path.join(context_dir, "designer→builder--架构设计.md")
        design_content = ""
        for p in [req_path, arch_path]:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    design_content += f"\n\n---\n\n### {os.path.basename(p)}\n\n{f.read()[:3000]}"

        # 如果有回退，读取 fix-prompt
        fix_content = ""
        if os.path.exists(fix_prompt_path):
            with open(fix_prompt_path, "r", encoding="utf-8") as f:
                fix_content = f.read()
            os.remove(fix_prompt_path)  # 读取后清除

        user_message = (
            f"需求：{state['requirement']}\n\n"
            f"设计文档内容：\n{design_content[:5000]}\n\n"
            + (f"修复指令（来自 Tester）：\n{fix_content}\n\n" if fix_content else "")
            + f"迭代次数：{iteration}/3（首次为 0）\n\n"
            + f"请完成以下任务：\n"
            f"1. 使用 write_code 工具将代码写入 `builder→tester--src/` 目录\n"
            f"2. 每个文件注明功能说明\n"
            + ("3. 根据修复指令修改代码，修复 Tester 发现的问题" if fix_content else "3. 确保代码语法正确，可以使用 run_command 检查")
        )

        raw_content = _invoke_agent(agent, user_message)

        entry["status"] = "completed"
        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        entry["summary"] = f"代码已生成（迭代 {iteration}/3）"
        entry["raw_output"] = raw_content

    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = str(e)

    outputs["builder"] = entry
    return {"agent_outputs": outputs, "current_agent": "builder"}


def tester_node(state: PipelineStateDict) -> dict:
    """Tester Agent — 质量验证。"""
    now = datetime.now(timezone.utc)
    context_dir = state["context_dir"]

    from .agents.tester import create_tester_agent

    designer_output = state.get("agent_outputs", {}).get("designer", {})
    builder_output = state.get("agent_outputs", {}).get("builder", {})

    test_report_path = os.path.join(context_dir, "tester→seller--测试报告.md")
    fix_prompt_path = os.path.join(context_dir, "tester→builder--修复指令.md")
    src_dir = os.path.join(context_dir, "builder→tester--src")

    entry = {
        "status": "running",
        "started_at": now.isoformat(),
        "retry_count": 0,
        "output_path": test_report_path,
        "summary": "",
        "raw_output": "",
        "error": None,
        "artifacts": [test_report_path],
        "completed_at": None,
    }

    outputs = dict(state.get("agent_outputs", {}))
    outputs["tester"] = entry
    save_state(_dict_to_pipeline_state({**state, "agent_outputs": outputs}))

    try:
        agent = create_tester_agent(context_dir=context_dir)

        # 读取设计文档
        req_path = os.path.join(context_dir, "designer→builder--需求分析.md")
        arch_path = os.path.join(context_dir, "designer→builder--架构设计.md")
        design_content = ""
        for p in [req_path, arch_path]:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    design_content += f"\n\n---\n\n### {os.path.basename(p)}\n\n{f.read()[:2000]}"

        # 列出 Builder 产出的代码文件
        code_files = []
        if os.path.exists(src_dir):
            for root, dirs, files in os.walk(src_dir):
                for fn in files:
                    code_files.append(os.path.join(root, fn))

        code_listing = "\n".join(code_files) if code_files else "（无代码文件）"

        user_message = (
            f"需求：{state['requirement']}\n\n"
            f"设计规格：\n{design_content[:4000]}\n\n"
            f"代码目录：{src_dir}\n"
            f"代码文件列表：\n{code_listing}\n\n"
            f"请完成以下任务：\n"
            f"1. 使用 read_file 工具读取代码文件，对照设计规格逐条检查\n"
            f"2. 使用 write_report 工具写入 `tester→seller--测试报告.md`\n"
            f"3. 如果存在不符合设计的功能，使用 write_report 工具写入 `tester→builder--修复指令.md`，说明：\n"
            f"   - 哪个功能不符合设计\n"
            f"   - 预期行为 vs 实际行为\n"
            f"   - 修复方向\n"
            f"如果所有功能都符合设计，不写入修复指令文件。"
        )

        raw_content = _invoke_agent(agent, user_message)

        entry["status"] = "completed"
        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        entry["summary"] = "测试报告已生成"
        entry["raw_output"] = raw_content

        # 检查是否有修复指令（判断是否需要回退）
        if os.path.exists(fix_prompt_path):
            entry["summary"] = "发现不符合设计的功能，已生成修复指令"
            entry["artifacts"] = [test_report_path, fix_prompt_path]
        else:
            # 如果测试报告不存在，尝试从 response 提取
            if not os.path.exists(test_report_path) and raw_content:
                os.makedirs(os.path.dirname(test_report_path), exist_ok=True)
                with open(test_report_path, "w", encoding="utf-8") as f:
                    f.write(raw_content)

    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = str(e)

    outputs["tester"] = entry
    return {"agent_outputs": outputs, "current_agent": "tester"}


def seller_node(state: PipelineStateDict) -> dict:
    """Seller Agent — 发布准备。"""
    now = datetime.now(timezone.utc)
    context_dir = state["context_dir"]

    from .agents.seller import create_seller_agent

    readme_path = os.path.join(context_dir, "seller→user--README.md")

    entry = {
        "status": "running",
        "started_at": now.isoformat(),
        "retry_count": 0,
        "output_path": readme_path,
        "summary": "",
        "raw_output": "",
        "error": None,
        "artifacts": [readme_path],
        "completed_at": None,
    }

    outputs = dict(state.get("agent_outputs", {}))
    outputs["seller"] = entry
    save_state(_dict_to_pipeline_state({**state, "agent_outputs": outputs}))

    try:
        agent = create_seller_agent(context_dir=context_dir)

        # 收集所有上游产出物路径
        artifacts_list = []
        for agent_name in ["scout", "designer", "builder", "tester"]:
            ao = outputs.get(agent_name, {})
            artifact_paths = ao.get("artifacts", [])
            for p in artifact_paths:
                if os.path.exists(p):
                    artifacts_list.append(p)

        artifacts_summary = "\n".join(f"- {p}" for p in artifacts_list)

        user_message = (
            f"项目名称：{state.get('project_name', '')}\n"
            f"需求：{state['requirement']}\n\n"
            f"所有上游产出物：\n{artifacts_summary}\n\n"
            f"请完成以下任务：\n"
            f"1. 使用 read_file 工具读取全部上游产出物\n"
            f"2. 使用 write_report 工具写入 `seller→user--README.md`\n"
            f"   - 项目简介\n"
            f"   - 安装方法\n"
            f"   - 使用示例（至少 3 个）\n"
            f"   - 架构概览\n"
            f"3. README 使用中文"
        )

        raw_content = _invoke_agent(agent, user_message)

        entry["status"] = "completed"
        entry["completed_at"] = datetime.now(timezone.utc).isoformat()
        entry["summary"] = "README 已生成"
        entry["raw_output"] = raw_content

        if not os.path.exists(readme_path) and raw_content:
            os.makedirs(os.path.dirname(readme_path), exist_ok=True)
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(raw_content)

    except Exception as e:
        entry["status"] = "failed"
        entry["error"] = str(e)

    outputs["seller"] = entry
    return {"agent_outputs": outputs, "current_agent": "seller"}


def finalize_node(state: PipelineStateDict) -> dict:
    """收尾节点 — 更新最终状态 + 持久化。"""
    now = datetime.now(timezone.utc)

    # 判定最终状态
    all_agents = ["scout", "designer", "builder", "tester", "seller"]
    ao = state.get("agent_outputs", {})
    agent_statuses = {name: ao.get(name, {}).get("status", "pending") for name in all_agents}
    any_failed = any(s == "failed" for s in agent_statuses.values())
    all_done = all(s in ("completed", "failed") for s in agent_statuses.values())

    if all_done:
        status = "failed" if any_failed else "completed"
    else:
        status = "running"

    updates = {
        "status": status,
        "updated_at": now.isoformat(),
        "current_agent": "finalize",
    }

    if any_failed:
        failed_agents = [name for name, s in agent_statuses.items() if s == "failed"]
        updates["warnings"] = [f"以下 Agent 执行失败：{', '.join(failed_agents)}"]

    # 写入迭代计数到 warning（如有多轮回退）
    iteration = state.get("iteration_count", 0)
    if iteration > 0:
        updates["warnings"] = [f"Builder-Tester 回退了 {iteration} 次"]

    return updates


# ============================================================
# 条件路由
# ============================================================

def route_after_tester(state: PipelineStateDict) -> str:
    """Tester 完成后的条件路由。

    如果存在修复指令文件，且回退次数未达上限 → 回退到 builder
    否则 → 前进到 seller
    """
    context_dir = state.get("context_dir", "")
    fix_prompt_path = os.path.join(context_dir, "tester→builder--修复指令.md")

    if os.path.exists(fix_prompt_path):
        iteration = state.get("iteration_count", 0)
        if iteration < 3:
            # 回退到 Builder（递增 iteration_count）
            return "builder"
        else:
            # 已达最大回退次数，前进到 Seller（带 warning）
            return "seller"
    else:
        return "seller"


# ============================================================
# StateGraph 构造器
# ============================================================

def create_orchestrator():
    """创建并编译完整的 LangGraph StateGraph。

    7 个节点 + 1 条条件边：

    START → parse → scout → designer → builder → tester
                                                    │
                                          ┌─────────┴─────────┐
                                          ▼                   ▼
                                      builder (回退)      seller → finalize → END
    """
    builder = StateGraph(PipelineStateDict)

    # 注册节点
    builder.add_node("parse", parse_node)
    builder.add_node("scout", scout_node)
    builder.add_node("designer", designer_node)
    builder.add_node("builder", builder_node)
    builder.add_node("tester", tester_node)
    builder.add_node("seller", seller_node)
    builder.add_node("finalize", finalize_node)

    # 主干边（线性）
    builder.add_edge(START, "parse")
    builder.add_edge("parse", "scout")
    builder.add_edge("scout", "designer")
    builder.add_edge("designer", "builder")
    builder.add_edge("builder", "tester")

    # 条件边：Tester → Builder（回退）或 → Seller（前进）
    builder.add_conditional_edges(
        "tester",
        route_after_tester,
        {
            "builder": "builder",
            "seller": "seller",
        },
    )

    builder.add_edge("seller", "finalize")
    builder.add_edge("finalize", END)

    # 编译（使用 MemorySaver 实现检查点）
    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


# ============================================================
# 状态转换：dict ↔ PipelineState
# ============================================================

def _dict_to_pipeline_state(d: dict) -> PipelineState:
    """将 PipelineStateDict 转为 PipelineState dataclass（用于 save_state）。"""
    ao_dict = d.get("agent_outputs", {}) or {}
    agent_outputs = {}
    for name, entry in ao_dict.items():
        agent_outputs[name] = AgentOutput(
            status=entry.get("status", "pending"),
            started_at=entry.get("started_at"),
            completed_at=entry.get("completed_at"),
            output_path=entry.get("output_path"),
            summary=entry.get("summary", ""),
            raw_output=entry.get("raw_output", ""),
            error=entry.get("error"),
            retry_count=entry.get("retry_count", 0),
            artifacts=entry.get("artifacts", []),
        )

    return PipelineState(
        requirement=d.get("requirement", ""),
        project_name=d.get("project_name", ""),
        project_slug=d.get("project_slug", ""),
        current_agent=d.get("current_agent", "scout"),
        phase="full_pipeline",
        agent_outputs=agent_outputs,
        status=d.get("status", "idle"),
        errors=d.get("errors", []),
        warnings=d.get("warnings", []),
        context_dir=d.get("context_dir", ""),
        knowledge_hit=d.get("knowledge_hit", False),
        knowledge_sources=d.get("knowledge_sources", []),
        pipeline_id=d.get("pipeline_id", ""),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


# ============================================================
# 主入口（向前兼容 Phase 1 接口）
# ============================================================

def run_pipeline(requirement: str, resume: bool = False) -> PipelineState:
    """Phase 2 Orchestrator：创建并运行 LangGraph StateGraph。

    Args:
        requirement: 用户输入的需求文本
        resume: 是否从已有流水线恢复（Phase 2 暂未支持完整恢复）

    Returns:
        PipelineState: 完整的流水线状态

    Raises:
        ValueError: 需求为空
    """
    if not requirement or not requirement.strip():
        raise ValueError("需求不能为空。请提供有效的需求描述。")

    # 初始化状态
    initial_state: PipelineStateDict = {
        "requirement": requirement.strip(),
        "agent_outputs": {},
        "errors": [],
        "warnings": [],
        "iteration_count": 0,
    }

    # 创建并运行图
    graph = create_orchestrator()

    # 生成唯一的线程 ID
    thread_id = uuid.uuid4().hex[:16]

    try:
        result = graph.invoke(
            initial_state,
            config={"configurable": {"thread_id": thread_id}},
        )
    except Exception as e:
        # 图执行失败，创建失败状态
        now = datetime.now(timezone.utc)
        fallback = PipelineState(
            requirement=requirement.strip(),
            status="failed",
            errors=[f"流水线执行异常：{str(e)}"],
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
        )
        fallback.pipeline_id = f"pl_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        fallback.project_name = extract_project_name(requirement)
        fallback.project_slug = slugify(fallback.project_name)
        fallback.context_dir = f"output/{fallback.project_slug}"
        os.makedirs(fallback.context_dir, exist_ok=True)
        fallback.agent_outputs["scout"] = AgentOutput(
            status="failed",
            error=str(e),
        )
        return fallback

    # 转为 PipelineState dataclass 并持久化
    pipeline_state = _dict_to_pipeline_state(result)
    try:
        save_state(pipeline_state)
    except Exception:
        pass  # 状态持久化失败不阻塞主流程

    return pipeline_state
