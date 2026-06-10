"""CLI 入口 — agent-pipeline 命令行工具 (Phase 2: 五 Agent 流水线)。

命令：
  run     启动流水线（五 Agent：Scout → Designer → Builder → Tester → Seller）
  status  查看流水线状态
  list    列出历史流水线
"""

import os
import sys
import time
from datetime import datetime, timezone

# 强制 UTF-8 输出，解决 Windows GBK 编码问题
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import click

# Agent 显示配置
AGENT_DISPLAY = {
    "scout": {"label": "Scout", "icon": "🔍", "name": "市场调研"},
    "designer": {"label": "Designer", "icon": "🎨", "name": "产品设计"},
    "builder": {"label": "Builder", "icon": "⚙️", "name": "编码实现"},
    "tester": {"label": "Tester", "icon": "🧪", "name": "质量验证"},
    "seller": {"label": "Seller", "icon": "📦", "name": "发布准备"},
}

AGENT_ORDER = ["scout", "designer", "builder", "tester", "seller"]


def _check_api_key():
    """检查 DEEPSEEK_API_KEY 环境变量，不存在则报错退出。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        click.echo(
            click.style("❌ 错误: ", fg="red", bold=True)
            + "未设置 DEEPSEEK_API_KEY 环境变量。\n"
            + "请设置后再运行:\n"
            + click.style("  export DEEPSEEK_API_KEY=sk-xxx", fg="yellow")
        )
        sys.exit(1)
    if len(api_key) < 10:
        click.echo(
            click.style("❌ 错误: ", fg="red", bold=True)
            + "DEEPSEEK_API_KEY 格式无效。\n"
            + "请检查是否设置了正确的 API Key。"
        )
        sys.exit(1)


def _print_pipeline_start(state):
    """打印流水线启动信息和五 Agent 看板。"""
    click.echo()
    click.echo(
        click.style("🚀 五 Agent 流水线已启动 ", fg="blue", bold=True)
        + click.style(f"(ID: {state.get('pipeline_id', 'N/A')})", dim=True)
    )
    click.echo(f"📋 需求: {click.style(state.get('requirement', '')[:80], bold=True)}")
    if len(state.get('requirement', '')) > 80:
        click.echo(f"   ...（共 {len(state['requirement'])} 字符）")
    project_slug = state.get('project_slug', '')
    if project_slug:
        click.echo(f"📁 项目: {click.style(project_slug, fg='cyan')}")
    if state.get("knowledge_hit"):
        click.echo(
            f"📚 知识库: {click.style('命中', fg='green')} "
            f"({len(state.get('knowledge_sources', []))} 条相关)"
        )

    # 五 Agent 看板
    click.echo()
    click.echo(click.style("📊 Agent 流水线:", bold=True))
    agent_icons = {
        "scout": "🔍", "designer": "🎨", "builder": "⚙️",
        "tester": "🧪", "seller": "📦",
    }
    agent_names = {
        "scout": "Scout", "designer": "Designer", "builder": "Builder",
        "tester": "Tester", "seller": "Seller",
    }
    agent_desc = {
        "scout": "市场调研", "designer": "产品设计", "builder": "编码实现",
        "tester": "质量验证", "seller": "发布准备",
    }

    for a in ["scout", "designer", "builder", "tester", "seller"]:
        icon = agent_icons.get(a, "⏳")
        name = agent_names.get(a, a)
        desc = agent_desc.get(a, "")
        status_dot = click.style("⏳", fg="white")
        click.echo(f"  {icon} {click.style(name, bold=True)} — {desc}  {status_dot}")

    click.echo()


def _print_agent_progress(agent_name: str, message: str, status: str = "running"):
    """打印 Agent 进度信息。"""
    icons = {"running": "⏳", "completed": "✅", "failed": "❌", "retry": "🔄"}
    colors = {"running": "blue", "completed": "green", "failed": "red", "retry": "yellow"}
    icon = icons.get(status, "⏳")
    color = colors.get(status, "blue")
    click.echo(f"  {click.style(icon, fg=color)} {message}")


def _print_all_agent_results(state, elapsed: float):
    """打印所有五个 Agent 的执行结果。"""
    click.echo()
    ao = state.agent_outputs if hasattr(state, 'agent_outputs') else state.get('agent_outputs', {})
    if not ao:
        return

    for agent_name in AGENT_ORDER:
        output = ao.get(agent_name, {})
        if isinstance(output, dict):
            status = output.get("status", "pending")
            err = output.get("error", "")
            summary = output.get("summary", "")
            retry = output.get("retry_count", 0)
        else:
            status = output.status if hasattr(output, 'status') else "pending"
            err = output.error if hasattr(output, 'error') else ""
            summary = output.summary if hasattr(output, 'summary') else ""
            retry = output.retry_count if hasattr(output, 'retry_count') else 0

        info = AGENT_DISPLAY.get(agent_name, {"label": agent_name, "icon": "❓", "name": ""})
        icon = info["icon"]

        if status == "completed":
            _print_agent_progress(
                agent_name,
                f"{icon} {info['label']} — {summary or info['name']}",
                "completed",
            )
        elif status == "failed":
            _print_agent_progress(
                agent_name,
                f"{icon} {info['label']} — 失败: {err or '未知错误'}",
                "failed",
            )
        elif status == "running":
            _print_agent_progress(
                agent_name,
                f"{icon} {info['label']} — 执行中",
                "running",
            )
        else:
            _print_agent_progress(
                agent_name,
                f"{icon} {info['label']} — 待执行",
                "running",
            )

        if retry > 0:
            _print_agent_progress(agent_name, f"  已重试 {retry} 次", "retry")

    # 产出物列表
    click.echo()
    click.echo(click.style("📄 产出物:", bold=True))
    for agent_name in AGENT_ORDER:
        output = ao.get(agent_name, {})
        if isinstance(output, dict):
            artifacts = output.get("artifacts", [])
            status = output.get("status", "pending")
        else:
            artifacts = output.artifacts if hasattr(output, 'artifacts') else []
            status = output.status if hasattr(output, 'status') else "pending"

        if status == "completed" and artifacts:
            for artifact_path in artifacts:
                if isinstance(artifact_path, str) and os.path.exists(artifact_path):
                    file_size = os.path.getsize(artifact_path)
                    size_str = f"{file_size / 1024:.1f} KB" if file_size > 0 else "0 B"
                    click.echo(f"  - {click.style(artifact_path, fg='cyan')} ({size_str})")
                elif isinstance(artifact_path, str):
                    click.echo(f"  - {click.style(artifact_path, fg='cyan')} (目录)")
        elif status == "completed":
            output_path = output.get("output_path", "") if isinstance(output, dict) else (output.output_path or "")
            if output_path and os.path.exists(output_path):
                file_size = os.path.getsize(output_path)
                size_str = f"{file_size / 1024:.1f} KB" if file_size > 0 else "0 B"
                click.echo(f"  - {click.style(output_path, fg='cyan')} ({size_str})")


def _print_pipeline_complete(state, elapsed: float):
    """打印流水线完成信息（Phase 2: 五 Agent 结果）。"""
    click.echo()

    # 获取最终状态
    if hasattr(state, 'status'):
        status = state.status
    elif isinstance(state, dict):
        status = state.get("status", "failed")
    else:
        status = "failed"

    if status == "completed":
        click.echo(
            click.style("✅ 五 Agent 流水线完成 ", fg="green", bold=True)
            + click.style(f"(总耗时: {elapsed:.1f}s)", dim=True)
        )
    elif status == "failed":
        click.echo(
            click.style("❌ 流水线失败 ", fg="red", bold=True)
            + click.style(f"(耗时: {elapsed:.1f}s)", dim=True)
        )
        # 打印错误
        if hasattr(state, 'errors'):
            errors = state.errors
        elif isinstance(state, dict):
            errors = state.get("errors", [])
        else:
            errors = []
        for err in errors:
            click.echo(f"  {click.style('•', fg='red')} {err}")

    # 打印所有 Agent 结果
    _print_all_agent_results(state, elapsed)

    # 打印警告
    if hasattr(state, 'warnings'):
        warnings = state.warnings
    elif isinstance(state, dict):
        warnings = state.get("warnings", [])
    else:
        warnings = []
    if warnings:
        click.echo()
        click.echo(click.style("⚠️  注意事项:", fg="yellow"))
        for w in warnings:
            click.echo(f"  {click.style('•', fg='yellow')} {w}")

    click.echo()


# ---- CLI 命令组 ----

@click.group()
@click.version_option(version="0.2.0", prog_name="agent-pipeline")
def cli():
    """Agent Pipeline — 五 Agent 开发流水线。

    用户输入产品需求 → 五个 Agent 依次执行：
    Scout(市场调研) → Designer(产品设计) → Builder(编码实现) → Tester(质量验证) → Seller(发布准备)
    """
    pass


@cli.command()
@click.argument("requirement", default="")
@click.option("--resume", is_flag=True, help="从最新断点恢复流水线")
def run(requirement: str, resume: bool):
    """启动五 Agent 流水线。

    REQUIREMENT 是你要调研的产品需求或问题。

    示例:

        agent-pipeline run "调研 AI 编码助手市场"

        agent-pipeline run "设计一个 TODO 应用"
    """
    # 检查 API Key
    _check_api_key()

    # 处理 resume
    if resume:
        from ..state import load_latest_state

        latest = load_latest_state()
        if latest is None:
            click.echo(
                click.style("❌ 错误: ", fg="red", bold=True)
                + "没有找到可恢复的流水线。"
            )
            sys.exit(1)
        if latest.status == "completed":
            click.echo(
                click.style("ℹ️  提示: ", fg="blue")
                + f"流水线 {latest.pipeline_id} 已完成，无需恢复。"
            )
            return

        requirement = latest.requirement
        click.echo(
            click.style("🔄 正在恢复流水线 ", fg="blue", bold=True)
            + f"(ID: {latest.pipeline_id})"
        )

    # 检查需求
    if not requirement or not requirement.strip():
        click.echo(
            click.style("❌ 错误: ", fg="red", bold=True) + "需求不能为空。\n"
            + "请提供需求描述，例如:\n"
            + click.style("  agent-pipeline run \"调研 AI 编码助手市场\"", fg="yellow")
        )
        sys.exit(1)

    # 截断超长需求
    if len(requirement) > 4096:
        click.echo(
            click.style("⚠️  提示: ", fg="yellow") + "需求超过 4096 字符，将截断处理。"
        )
        requirement = requirement[:4096]

    # 启动流水线
    click.echo()
    click.echo(click.style("正在启动五 Agent 流水线...", fg="blue", bold=True))

    # 先打印看板（初始状态）
    from ..orchestrator import run_pipeline
    from ..models import PipelineState

    # 准备启动信息
    from ..orchestrator import extract_project_name, slugify
    project_name = extract_project_name(requirement)
    project_slug = slugify(project_name)
    from datetime import datetime, timezone
    import uuid
    preview_state = {
        "pipeline_id": f"pl_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "requirement": requirement,
        "project_slug": project_slug,
        "knowledge_hit": False,
        "knowledge_sources": [],
    }
    _print_pipeline_start(preview_state)

    start_time = time.time()

    try:
        state = run_pipeline(requirement, resume=resume)
    except ValueError as e:
        click.echo(
            click.style("❌ 错误: ", fg="red", bold=True) + str(e)
        )
        sys.exit(1)
    except Exception as e:
        click.echo(
            click.style("❌ 流水线异常: ", fg="red", bold=True) + str(e)
        )
        if os.environ.get("AGENT_PIPELINE_DEBUG"):
            import traceback
            traceback.print_exc()
        sys.exit(1)

    elapsed = time.time() - start_time

    # 输出结果
    _print_pipeline_complete(state, elapsed)

    # 返回状态码
    if state.status == "failed":
        sys.exit(1)


@cli.command()
@click.argument("pipeline_id", default="")
def status(pipeline_id: str):
    """查看流水线状态。

    显示当前或指定流水线的运行状态、耗时、五 Agent 执行情况。
    """
    from ..state import load_latest_state, load_state, list_pipelines

    state = None
    if pipeline_id:
        pipelines = list_pipelines(limit=50)
        for p in pipelines:
            if p.pipeline_id == pipeline_id:
                state = p
                break
        if state is None:
            click.echo(
                click.style("❌ 错误: ", fg="red", bold=True)
                + f"未找到流水线 {pipeline_id}。"
            )
            sys.exit(1)
    else:
        state = load_latest_state()
        if state is None:
            click.echo(
                click.style("📭 提示: ", fg="blue") + "暂无流水线记录。\n"
                + "运行以下命令启动第一个流水线:\n"
                + click.style('  agent-pipeline run "调研需求"', fg="yellow")
            )
            return

    # 打印状态
    status_colors = {
        "idle": "blue",
        "running": "cyan",
        "completed": "green",
        "failed": "red",
    }
    status_icons = {
        "idle": "⏸️",
        "running": "▶️",
        "completed": "✅",
        "failed": "❌",
    }

    click.echo()
    click.echo(
        click.style(f"流水线状态 ", bold=True)
        + click.style(f"({state.pipeline_id})", dim=True)
    )
    icon = status_icons.get(state.status, "❓")
    color = status_colors.get(state.status, "white")
    click.echo(f"  状态: {click.style(icon + ' ' + state.status, fg=color, bold=True)}")
    click.echo(f"  需求: {state.requirement[:60]}{'...' if len(state.requirement) > 60 else ''}")
    click.echo(f"  项目: {state.project_slug}")

    # 五 Agent 状态
    if state.agent_outputs:
        click.echo(f"  Agent 执行情况:")
        for agent_name in AGENT_ORDER:
            output = state.agent_outputs.get(agent_name)
            if not output:
                continue

            a_color = status_colors.get(output.status, "white")
            a_icon = status_icons.get(output.status, "⏳")
            info = AGENT_DISPLAY.get(agent_name, {"label": agent_name, "icon": "❓"})
            click.echo(
                f"    {info['icon']} {click.style(info['label'], bold=True)}: "
                + click.style(output.status, fg=a_color)
                + (f" · {output.summary}" if output.summary else "")
            )

    click.echo()


@cli.command()
@click.option("--limit", default=20, help="显示最近 N 条记录")
def list(limit: int):
    """列出历史流水线记录。"""
    from ..state import list_pipelines

    pipelines = list_pipelines(limit=limit)

    if not pipelines:
        click.echo(
            click.style("📭 提示: ", fg="blue") + "暂无流水线记录。\n"
            + "运行以下命令启动第一个流水线:\n"
            + click.style('  agent-pipeline run "调研需求"', fg="yellow")
        )
        return

    click.echo()
    click.echo(click.style(f"最近 {min(limit, len(pipelines))} 条流水线记录", bold=True))
    click.echo()

    # 表头
    click.echo(
        click.style(f"{'ID':<25} {'状态':<12} {'项目':<25} {'时间':<20}", bold=True)
    )
    click.echo("-" * 82)

    for p in pipelines:
        status_color = {
            "idle": "blue",
            "running": "cyan",
            "completed": "green",
            "failed": "red",
        }.get(p.status, "white")
        status_icon = {
            "idle": "⏸️",
            "running": "▶️",
            "completed": "✅",
            "failed": "❌",
        }.get(p.status, "❓")

        created = p.created_at[:19] if p.created_at else "N/A"
        click.echo(
            f"{p.pipeline_id:<25} "
            + click.style(f"{status_icon} {p.status:<9}", fg=status_color)
            + f"{p.project_slug[:24]:<25} "
            + f"{created:<20}"
        )

    click.echo()


@cli.command()
@click.option("--port", default=3456, help="Web 服务端口")
@click.option("--no-open", is_flag=True, help="不自动打开浏览器")
def serve(port: int, no_open: bool):
    """启动 Web 服务（FastAPI + SSE + Eclipse 熄灯）。

    打开浏览器访问 Web UI，支持实时查看流水线执行进度。

    示例:

        agent-pipeline serve

        agent-pipeline serve --port 8080 --no-open
    """
    import webbrowser

    if not no_open:
        webbrowser.open(f"http://localhost:{port}")

    click.echo(
        click.style("🌐 Agent Pipeline Web 服务已启动 ", fg="green", bold=True)
        + click.style(f"(http://localhost:{port})", bold=True)
    )
    click.echo("按 Ctrl+C 停止服务")

    import uvicorn

    uvicorn.run(
        "agent_pipeline.web.server:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    cli()
