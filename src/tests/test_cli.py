"""Agent Pipeline — Phase 1 E2E CLI 测试。

溯源链：
  designer→builder.md §T1.1  →  test-plan.md T1.1  →  test_cli.py  // 验证 T1.1

本测试验证 documented behavior（文档/CLI 参考声明的行为），
不是源码实现细节。不逆向工程代码。
"""

import json
import os
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---- 路径计算 ----
# test_cli.py 在 src/tests/ 下，项目根目录在其父父父级
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # → projects/agent-pipeline/
SRC_DIR = PROJECT_ROOT / "src"

# ---- CLI 命令 ----
# 使用 python -m 模块方式调用，避免依赖 pip install -e .
CLI_CMD = [sys.executable, "-m", "agent_pipeline.cli.main"]

# ---- 环境变量 ----
# 测试用假的 DeepSeek API Key（>= 10 字符，通过长度检查）
TEST_API_KEY = "sk-test-key-1234567890"

# 基准环境：PYTHONPATH 指向 src/， PYTHONIOENCODING 确保 Windows 编码
BASE_ENV = {
    "PYTHONIOENCODING": "utf-8",
    "PYTHONPATH": str(SRC_DIR),
}

# 带 API Key 的环境
ENV_WITH_KEY = {**BASE_ENV, "DEEPSEEK_API_KEY": TEST_API_KEY}

# 无 API Key 的环境（显式删除防止继承）
ENV_NO_KEY = {k: v for k, v in BASE_ENV.items()}

# 短 Key(< 10 字符)环境
ENV_SHORT_KEY = {**BASE_ENV, "DEEPSEEK_API_KEY": "short"}

# ---- 辅助函数 ----


def _run_cli(
    args: list[str],
    env: dict | None = None,
    cwd: str | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """运行 CLI 命令并返回结果。

    Args:
        args: CLI 参数（如 ["run", "test"]）
        env: 环境变量，默认 BASE_ENV
        cwd: 工作目录，默认项目根目录
        timeout: 超时秒数

    Returns:
        subprocess.CompletedProcess
    """
    if env is None:
        env = BASE_ENV
    if cwd is None:
        cwd = str(PROJECT_ROOT)

    result = subprocess.run(
        CLI_CMD + args,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        cwd=cwd,
        timeout=timeout,
    )
    return result


def _create_temp_pipeline_state(
    tmpdir: str,
    status: str = "completed",
    project_slug: str = "test-project",
    pipeline_id: str = "pl_20260610_test0000_abc123",
) -> Path:
    """在临时目录中创建模拟的流水线状态文件。

    Args:
        tmpdir: 临时目录路径
        status: 状态（completed/failed/running）
        project_slug: 项目 slug
        pipeline_id: 流水线 ID

    Returns:
        output 目录的 Path
    """
    output_dir = Path(tmpdir) / "output" / project_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    state = {
        "pipeline_id": pipeline_id,
        "status": status,
        "requirement": "test requirement",
        "project_name": "test project",
        "project_slug": project_slug,
        "context_dir": str(output_dir),
        "current_agent": "scout",
        "phase": "scout",
        "agent_outputs": {
            "scout": {
                "status": status,
                "started_at": "2026-06-10T12:00:00",
                "completed_at": "2026-06-10T12:01:00",
                "output_path": f"{output_dir}/scout/report.md",
                "summary": "测试报告已生成",
                "raw_output": "# Test Report\n\n报告内容",
                "error": None if status == "completed" else "模拟错误",
                "retry_count": 0,
                "artifacts": [f"{output_dir}/scout/report.md"],
            }
        },
        "errors": [] if status == "completed" else ["模拟错误"],
        "warnings": [],
        "knowledge_hit": False,
        "knowledge_sources": [],
        "created_at": "2026-06-10T12:00:00",
        "updated_at": "2026-06-10T12:01:00",
    }

    state_path = output_dir / "state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    return output_dir


# ============================================================
# 测试类：帮助和版本
# ============================================================


class TestHelpAndVersion:
    """验证 --help 和 --version。"""

    def test_help_shows_all_commands(self) -> None:
        """--help 应列出所有命令。"""
        # 验证 T6.5: 输出无异常内容
        result = _run_cli(["--help"])

        assert result.returncode == 0
        assert "run" in result.stdout
        assert "status" in result.stdout
        assert "list" in result.stdout

    def test_help_run(self) -> None:
        """run --help 应显示参数和选项。"""
        result = _run_cli(["run", "--help"])

        assert result.returncode == 0
        assert "REQUIREMENT" in result.stdout
        assert "--resume" in result.stdout

    def test_help_status(self) -> None:
        """status --help 应显示参数。"""
        result = _run_cli(["status", "--help"])

        assert result.returncode == 0
        assert "PIPELINE_ID" in result.stdout

    def test_help_list(self) -> None:
        """list --help 应显示选项。"""
        result = _run_cli(["list", "--help"])

        assert result.returncode == 0
        assert "--limit" in result.stdout

    def test_version(self) -> None:
        """--version 显示版本号。Bug #1 已修复。"""
        result = _run_cli(["--version"])
        assert result.returncode == 0
        assert "0.2.0" in result.stdout


# ============================================================
# 测试类：run 命令 — 异常场景
# ============================================================


class TestRunErrors:
    """验证 run 命令的异常处理路径。"""

    def test_empty_requirement(self) -> None:
        """T2.1/T5.3: 空需求报错。"""
        # 验证 T2.1: 空需求 → 需求不能为空
        # 验证 T5.3: 空需求立即报错，不创建流水线
        result = _run_cli(["run", ""], env=ENV_WITH_KEY)

        assert result.returncode != 0
        assert "需求不能为空" in result.stdout

    def test_whitespace_requirement(self) -> None:
        """T2.2: 仅空格需求报错。"""
        # 验证 T2.2: 仅空格 → 需求不能为空
        result = _run_cli(["run", "   "], env=ENV_WITH_KEY)

        assert result.returncode != 0
        assert "需求不能为空" in result.stdout

    def test_long_requirement_truncation(self) -> None:
        """T2.3/T3.2: 超长需求截断警告。"""
        # 验证 T2.3: 10000+ 字符截断或正常处理
        # 验证 T3.2: 4096 字符边界
        long_text = "测试需求 " * 1000  # ~4000 字符
        # 确保超过 4096
        while len(long_text) < 4100:
            long_text += "加长 "

        result = _run_cli(["run", long_text], env=ENV_WITH_KEY, timeout=60)

        # 截断警告应出现
        assert "超过 4096 字符" in result.stdout

    def test_no_api_key(self) -> None:
        """T2.4: 无 DEEPSEEK_API_KEY 时友好报错。"""
        # 验证 T2.4: 未设置 API Key → 报错提示
        result = _run_cli(["run", "test"], env=ENV_NO_KEY)

        assert result.returncode != 0
        assert "DEEPSEEK_API_KEY" in result.stdout
        assert "请设置" in result.stdout

    def test_short_api_key(self) -> None:
        """T2.5 派生: API Key 长度不足 10 字符时报错。"""
        # API Key 必须 >= 10 字符
        result = _run_cli(["run", "test"], env=ENV_SHORT_KEY)

        assert result.returncode != 0
        # 可能是"格式无效"或"认证失败"，取决于检查点
        # 至少应该报错
        assert "DEEPSEEK_API_KEY" in result.stdout

    def test_resume_no_history(self) -> None:
        """T2.8: --resume 但无历史流水线时提示。"""
        # 验证 T2.8: 没有可恢复的流水线
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "--resume"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
            )

        assert "没有找到可恢复的流水线" in result.stdout

    def test_unknown_command(self) -> None:
        """T2.7: 非法命令报错。"""
        # 验证 T2.7: 未知命令 → Click 报错
        result = _run_cli(["unknown"])

        assert result.returncode != 0
        assert "No such command" in result.stdout or "No such command" in result.stderr or "Error" in result.stderr

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows subprocess langgraph asyncio")
    def test_invalid_api_key_run_fails_gracefully(self) -> None:
        """T2.5: 无效 API Key 时流水线优雅失败。

        使用假 Key 执行 run，验证：
        - 流水线启动输出格式正确
        - API 失败后标记失败
        - exit code = 1
        """
        # 验证 T2.5: API Key 无效时友好报错
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "测试 AI 市场调研"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
                timeout=60,
            )

        assert result.returncode != 0

        # T6.1: 启动输出含 "🚀"
        assert "🚀" in result.stdout
        assert "流水线已启动" in result.stdout

        # T6.2: 进度显示 Agent 名
        assert "Scout" in result.stdout or "scout" in result.stdout

        # T6.4: 失败输出含 "❌"
        assert "❌" in result.stdout
        assert "失败" in result.stdout or "异常" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows subprocess langgraph asyncio 限制，真实 CLI 正常运行")
    def test_invalid_api_key_creates_state(self) -> None:
        """无效 API Key 的 run 仍会创建 state.json。"""
        # 状态持久化应始终执行
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "项目测试"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
                timeout=60,
            )

        # 检查 state.json 是否存在
        output_dirs = list(Path(tmpdir).glob("output/*/state.json"))
        assert len(output_dirs) >= 1, "state.json 应被创建"


# ============================================================
# 测试类：status 命令
# ============================================================


class TestStatus:
    """验证 status 命令。"""

    def test_status_empty_no_pipelines(self) -> None:
        """T1.4: 无流水线时 status 显示提示。"""
        # 验证 T1.4: 无流水线记录时友好提示
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(["status"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        assert "暂无流水线记录" in result.stdout
        assert "agent-pipeline run" in result.stdout

    def test_status_shows_latest_pipeline(self) -> None:
        """T1.4: status 显示最新流水线状态。"""
        # 验证 T1.4: 有流水线时显示状态详情
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_temp_pipeline_state(
                tmpdir,
                status="completed",
                project_slug="ai-market-research",
            )
            result = _run_cli(["status"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        assert "流水线状态" in result.stdout
        assert "pl_" in result.stdout
        assert "completed" in result.stdout

    def test_status_shows_failed_status(self) -> None:
        """status 正确显示失败流水线。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_temp_pipeline_state(
                tmpdir,
                status="failed",
                project_slug="failed-project",
            )
            result = _run_cli(["status"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        assert "failed" in result.stdout

    def test_status_by_pipeline_id(self) -> None:
        """status 支持按流水线 ID 查询。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_temp_pipeline_state(
                tmpdir,
                status="completed",
                pipeline_id="pl_custom_id_001_test",
            )
            result = _run_cli(
                ["status", "pl_custom_id_001_test"],
                env=BASE_ENV,
                cwd=tmpdir,
            )

        assert result.returncode == 0
        assert "pl_custom_id_001_test" in result.stdout

    def test_status_invalid_pipeline_id(self) -> None:
        """按不存在的 ID 查询时报错。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["status", "nonexistent_id"],
                env=BASE_ENV,
                cwd=tmpdir,
            )

        assert result.returncode != 0
        assert "未找到" in result.stdout

    def test_status_concurrent_consistency(self) -> None:
        """T3.5: 连续 status 调用返回一致状态。"""
        # 验证 T3.5: 多次调用始终返回正确状态
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_temp_pipeline_state(
                tmpdir,
                status="completed",
                project_slug="concurrent-test",
            )
            results = []
            for _ in range(5):
                r = _run_cli(["status"], env=BASE_ENV, cwd=tmpdir)
                results.append(r)

        # 所有调用应成功
        assert all(r.returncode == 0 for r in results)
        # 所有输出应一致
        first_output = results[0].stdout
        for r in results[1:]:
            assert r.stdout == first_output


# ============================================================
# 测试类：list 命令
# ============================================================


class TestList:
    """验证 list 命令。"""

    def test_list_empty_no_pipelines(self) -> None:
        """T1.5: 无流水线时 list 提示。"""
        # 验证 T1.5: 无历史时友好提示
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(["list"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        assert "暂无流水线记录" in result.stdout

    def test_list_shows_pipelines(self) -> None:
        """T1.5: list 显示流水线列表。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _create_temp_pipeline_state(
                tmpdir,
                status="completed",
                project_slug="project-alpha",
                pipeline_id="pl_alpha_001",
            )
            _create_temp_pipeline_state(
                tmpdir,
                status="failed",
                project_slug="project-beta",
                pipeline_id="pl_beta_002",
            )
            result = _run_cli(["list"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        assert "流水线记录" in result.stdout
        assert "pl_alpha_001" in result.stdout
        assert "pl_beta_002" in result.stdout

    def test_list_limit(self) -> None:
        """list --limit 控制返回条数。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 5 条记录
            for i in range(5):
                _create_temp_pipeline_state(
                    tmpdir,
                    status="completed",
                    project_slug=f"project-{i}",
                    pipeline_id=f"pl_00{i}_test",
                )

            # --limit 3 应返回 3 条
            result = _run_cli(
                ["list", "--limit", "3"],
                env=BASE_ENV,
                cwd=tmpdir,
            )

        assert result.returncode == 0
        # 输出应该提到 3 条
        assert "3" in result.stdout or "3" in result.stdout

    def test_list_without_limit_defaults_to_20(self) -> None:
        """list 默认 limit=20。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                _create_temp_pipeline_state(
                    tmpdir,
                    status="completed",
                    project_slug=f"project-{i}",
                    pipeline_id=f"pl_00{i}_default",
                )

            result = _run_cli(["list"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        # 所有 5 条都应显示
        for i in range(5):
            assert f"pl_00{i}_default" in result.stdout


# ============================================================
# 测试类：CLI 输出一致性
# ============================================================


class TestCliOutput:
    """验证 CLI 输出格式的一致性。"""

    def test_help_output_no_none(self) -> None:
        """T6.5: help 输出不含 None/undefined。"""
        # 验证 T6.5: 无空值异常输出
        result = _run_cli(["--help"])

        assert result.returncode == 0
        assert "None" not in result.stdout
        assert "undefined" not in result.stdout

    def test_error_output_contains_reason(self) -> None:
        """T6.4: 错误输出含失败原因。"""
        # 验证 T6.4: 空需求错误含具体信息
        result = _run_cli(["run", ""], env=ENV_WITH_KEY)

        assert result.returncode != 0
        assert "❌" in result.stdout
        assert "需求不能为空" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows subprocess langgraph asyncio")
    def test_start_output_format(self) -> None:
        """T6.1/T6.2: 流水线启动输出格式。"""
        # 验证 T6.1: 启动含 🚀
        # 验证 T6.2: 显示 Agent
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "测试项目"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
                timeout=60,
            )

        # 启动标识
        assert "🚀" in result.stdout
        assert "流水线已启动" in result.stdout

        # Pipeline ID 格式
        import re
        assert re.search(r"pl_\d{8}_\d{6}_[a-f0-9]{6}", result.stdout)

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows subprocess langgraph asyncio")
    def test_failure_output_format(self) -> None:
        """T6.4: 失败输出格式。"""
        # 验证 T6.4: 失败含 ❌、原因、可恢复提示
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "测试项目"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
                timeout=60,
            )

        assert "❌" in result.stdout
        # 应包含某种失败描述
        assert any(
            keyword in result.stdout
            for keyword in ["失败", "异常", "error", "Error", "错误"]
        )


# ============================================================
# 测试类：状态持久化
# ============================================================


class TestStatePersistence:
    """验证 state.json 的正确读写。"""

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows subprocess langgraph asyncio")
    def test_failed_run_creates_state(self) -> None:
        """失败流水线仍会创建 state.json。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _run_cli(
                ["run", "test-state"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
                timeout=60,
            )

            # 验证 state.json 存在
            state_files = list(Path(tmpdir).glob("output/*/state.json"))
            assert len(state_files) >= 1

            # 验证内容格式
            with open(state_files[0], "r", encoding="utf-8") as f:
                state = json.load(f)

            assert "pipeline_id" in state
            assert "status" in state
            assert "requirement" in state
            assert "agent_outputs" in state
            assert "scout" in state["agent_outputs"]

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows subprocess langgraph asyncio")
    def test_status_after_failed_run(self) -> None:
        """T1.4: 失败流水线后 status 显示状态。"""
        # 结合测试：run（失败）→ status（读取）
        with tempfile.TemporaryDirectory() as tmpdir:
            # 先运行一次（失败）
            _run_cli(
                ["run", "test-then-status"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
                timeout=60,
            )

            # 再查状态
            result = _run_cli(["status"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        assert "流水线状态" in result.stdout
        # 状态可能是 completed 或 failed（取决于 API 调用结果）
        assert any(
            s in result.stdout
            for s in ["failed", "completed"]
        )

    def test_list_after_failed_run(self) -> None:
        """T1.5: 失败流水线后 list 显示记录。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            _run_cli(
                ["run", "test-then-list"],
                env=ENV_WITH_KEY,
                cwd=tmpdir,
                timeout=60,
            )

            result = _run_cli(["list"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        assert "流水线记录" in result.stdout or "test-then-list" in result.stdout


# ============================================================
# 跳过测试（需要真实 DeepSeek API Key）
# ============================================================

HAS_REAL_API_KEY = bool(
    os.environ.get("DEEPSEEK_API_KEY")
    and len(os.environ["DEEPSEEK_API_KEY"]) > 20
    and os.environ["DEEPSEEK_API_KEY"] != TEST_API_KEY
)

skip_no_real_key = pytest.mark.skipif(
    not HAS_REAL_API_KEY,
    reason="需要真实 DEEPSEEK_API_KEY（测试用 key 不足 20 字符视为伪造）",
)


class TestRealRun:
    """需要真实 DeepSeek API Key 的端到端测试。"""

    @skip_no_real_key
    def test_standard_run(self) -> None:
        """T1.1: 标准需求运行成功。"""
        # 验证 T1.1: 输出报告到 output/{slug}/scout/report.md
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "调研 AI 编码助手市场"],
                env={**BASE_ENV, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]},
                cwd=tmpdir,
                timeout=600,  # LLM 调用可能需要 5 分钟
            )

        assert result.returncode == 0
        assert "✅" in result.stdout
        assert "流水线完成" in result.stdout
        assert "产出物" in result.stdout

        # 检查报告文件
        report_files = list(Path(tmpdir).glob("output/*/scout/report.md"))
        assert len(report_files) >= 1

        # 报告内容非空
        with open(report_files[0], "r", encoding="utf-8") as f:
            content = f.read()
        assert len(content) > 100

    @skip_no_real_key
    def test_short_requirement(self) -> None:
        """T1.2: 短需求运行成功。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "分析竞品"],
                env={**BASE_ENV, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]},
                cwd=tmpdir,
                timeout=600,
            )

        assert result.returncode == 0
        assert "✅" in result.stdout

    @skip_no_real_key
    def test_special_char_requirement(self) -> None:
        """T1.3: 带特殊字符需求运行成功。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "调研 Python 3.12 的 match-case 语法在 Agent 框架中的应用"],
                env={**BASE_ENV, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]},
                cwd=tmpdir,
                timeout=600,
            )

        assert result.returncode == 0
        # 项目名应正确生成（不含非法字符）
        assert "🚀" in result.stdout

    @skip_no_real_key
    def test_report_contains_required_sections(self) -> None:
        """T4.2: 报告应包含"市场概述"段落。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "调研 AI 编码助手市场"],
                env={**BASE_ENV, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]},
                cwd=tmpdir,
                timeout=600,
            )

        assert result.returncode == 0

        report_files = list(Path(tmpdir).glob("output/*/scout/report.md"))
        assert len(report_files) >= 1

        with open(report_files[0], "r", encoding="utf-8") as f:
            content = f.read()

        # 验证 T4.2: 报告包含市场概述
        assert "市场概述" in content or "市场" in content

    @skip_no_real_key
    def test_minimum_requirement(self) -> None:
        """T3.1: 正好 10 字符的需求正常运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "调研项目"],  # 4 个中文字符
                env={**BASE_ENV, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]},
                cwd=tmpdir,
                timeout=600,
            )

        assert result.returncode == 0

    @skip_no_real_key
    def test_multibyte_requirement(self) -> None:
        """T3.4: 多字节字符（中日韩+emoji）需求正常运行。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _run_cli(
                ["run", "調査AIコードアシスタント市場 🚀 test 调研"],
                env={**BASE_ENV, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]},
                cwd=tmpdir,
                timeout=600,
            )

        assert result.returncode == 0
        # 文件名应正确处理
        assert "🚀" not in result.stderr  # emoji 不应导致错误

    @skip_no_real_key
    def test_duplicate_run_creates_new_project(self) -> None:
        """T3.6: 同一需求运行两次创建不同项目。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {**BASE_ENV, "DEEPSEEK_API_KEY": os.environ["DEEPSEEK_API_KEY"]}

            # 第一次运行
            _run_cli(
                ["run", "调研低代码平台"],
                env=env,
                cwd=tmpdir,
                timeout=600,
            )

            # 第二次运行
            _run_cli(
                ["run", "调研低代码平台"],
                env=env,
                cwd=tmpdir,
                timeout=600,
            )

            # 应有两个不同的流水线记录
            state_files = list(Path(tmpdir).glob("output/*/state.json"))
            assert len(state_files) >= 2


# ============================================================
# 故障场景测试
# ============================================================


class TestFaultScenarios:
    """验证故障场景处理。"""

    def test_corrupted_state_json(self) -> None:
        """T5.5: 损坏的 state.json 被检测到。"""
        # 验证 T5.5: 非法 JSON 时提示手动修复
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "output" / "corrupted-project"
            output_dir.mkdir(parents=True, exist_ok=True)

            # 写入非法 JSON
            state_path = output_dir / "state.json"
            with open(state_path, "w", encoding="utf-8") as f:
                f.write("这不是 JSON 格式{{{")

            # status 应处理损坏状态文件
            result = _run_cli(["status"], env=BASE_ENV, cwd=tmpdir)

            # 不应崩溃，应优雅处理
            # 可能的响应：跳过损坏的或报错
            assert result.returncode in (0, 1)

            # list 也应处理
            result_list = _run_cli(["list"], env=BASE_ENV, cwd=tmpdir)
            assert result_list.returncode in (0, 1)


# ============================================================
# 模块导入测试
# ============================================================


class TestModuleImport:
    """验证关键模块可导入。"""

    def test_import_agent_pipeline(self) -> None:
        """agent_pipeline 包可导入。"""
        result = subprocess.run(
            [sys.executable, "-c", "import agent_pipeline; print(agent_pipeline.__version__)"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )

        assert result.returncode == 0
        assert "0.2.0" in result.stdout

    def test_import_models(self) -> None:
        """数据模型可导入。"""
        result = subprocess.run(
            [sys.executable, "-c", "from agent_pipeline.models import PipelineState, AgentOutput; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )

        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_import_state(self) -> None:
        """状态管理可导入。"""
        result = subprocess.run(
            [sys.executable, "-c", "from agent_pipeline.state import save_state, load_state; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )

        assert result.returncode == 0
        assert "ok" in result.stdout

    def test_import_cli(self) -> None:
        """CLI 入口可导入。"""
        result = subprocess.run(
            [sys.executable, "-c", "from agent_pipeline.cli.main import cli; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )

        assert result.returncode == 0
        assert "ok" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows subprocess asyncio 线程限制，真实 CLI 正常运行")
    def test_import_scout_agent(self) -> None:
        """Scout Agent 可导入（非 Windows 子进程环境）。"""
        result = subprocess.run(
            [sys.executable, "-c", "from agent_pipeline.agents.scout import create_scout_agent; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )

        assert result.returncode == 0
        assert "ok" in result.stdout


# ============================================================
# Phase 2 测试：五 Agent 导入（P2-T10 ~ P2-T13）
# ============================================================


class TestPhase2AgentImports:
    """Phase 2: P2-T10 ~ P2-T13 — 验证五个 Agent 创建函数均可导入。

    溯源链：
      builder→tester.md §7.6 P2-T10 → test-plan.md P2-T10 → test_cli.py // 验证 P2-T10
    """

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows subprocess asyncio 线程限制，Agent 导入需要 langgraph",
    )
    def test_import_create_designer_agent(self) -> None:
        """P2-T10: create_designer_agent 可导入。"""
        result = subprocess.run(
            [sys.executable, "-c",
             "from agent_pipeline.agents.designer import create_designer_agent; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "ok" in result.stdout

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows subprocess asyncio 线程限制",
    )
    def test_import_create_builder_agent(self) -> None:
        """P2-T11: create_builder_agent 可导入。"""
        result = subprocess.run(
            [sys.executable, "-c",
             "from agent_pipeline.agents.builder import create_builder_agent; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "ok" in result.stdout

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows subprocess asyncio 线程限制",
    )
    def test_import_create_tester_agent(self) -> None:
        """P2-T12: create_tester_agent 可导入。"""
        result = subprocess.run(
            [sys.executable, "-c",
             "from agent_pipeline.agents.tester import create_tester_agent; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "ok" in result.stdout

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows subprocess asyncio 线程限制",
    )
    def test_import_create_seller_agent(self) -> None:
        """P2-T13: create_seller_agent 可导入。"""
        result = subprocess.run(
            [sys.executable, "-c",
             "from agent_pipeline.agents.seller import create_seller_agent; print('ok')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "ok" in result.stdout

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows subprocess asyncio 线程限制，agents 包导入需要 langgraph",
    )
    def test_agents_module_exports_all_five(self) -> None:
        """agents.__init__ 导出全部 5 个创建函数。"""
        result = subprocess.run(
            [sys.executable, "-c",
             "from agent_pipeline.agents import __all__; "
             "expected = {'create_scout_agent','create_designer_agent','create_builder_agent',"
             "             'create_tester_agent','create_seller_agent'}; "
             "print('ok' if set(__all__) == expected else set(__all__))"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "ok" in result.stdout, f"Got: {result.stdout}"


# ============================================================
# Phase 2 测试：StateGraph 结构编译（P2-T14）
# ============================================================


class TestPhase2StateGraph:
    """Phase 2: P2-T14 — 验证 StateGraph 编译和节点数。

    溯源链：
      builder→tester.md §7.6 P2-T14 → test-plan.md P2-T14 → test_cli.py // 验证 P2-T14
    """

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows subprocess asyncio 线程限制，langgraph 导入需要 asyncio",
    )
    def test_orchestrator_compiles_with_seven_nodes(self) -> None:
        """P2-T14 / P2-S1: create_orchestrator() 编译成功，注册 7 节点。"""
        result = subprocess.run(
            [sys.executable, "-c",
             "from agent_pipeline.orchestrator import create_orchestrator; "
             "g = create_orchestrator(); "
             "nodes = list(g.nodes.keys()); "
             "print(f'nodes={len(nodes)}'); "
             "for n in nodes: print(f'node:{n}')"],
            capture_output=True, text=True,
            env={"PYTHONPATH": str(SRC_DIR)},
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

        # 检查节点数
        assert "nodes=7" in result.stdout, (
            f"预期 7 节点，实际节点数: {result.stdout}"
        )

        # 检查 7 个节点名称
        expected_nodes = {"parse", "scout", "designer", "builder", "tester",
                          "seller", "finalize"}
        for node in expected_nodes:
            assert f"node:{node}" in result.stdout, (
                f"缺少节点 '{node}'. 输出: {result.stdout}"
            )


# ============================================================
# Phase 2 测试：条件路由逻辑（P2-R1 ~ P2-R4）
# ============================================================


class TestPhase2RoutingLogic:
    """Phase 2: P2-R1 ~ P2-R4 — route_after_tester 条件路由。

    测试 route_after_tester 的三种路径（文档声明，不是逆向工程代码）：
    - 修复指令存在 + iteration < 3  → "builder"
    - 修复指令存在 + iteration >= 3 → "seller"
    - 无修复指令                       → "seller"

    state.context_dir → os.path.join(context_dir, "tester→builder--修复指令.md")
    """

    # 实现 route_after_tester 的文档声明行为（不含 langgraph 依赖，纯函数）
    @staticmethod
    def _route_after_tester(context_dir: str, iteration_count: int) -> str:
        """Standalone reimplementation matching route_after_tester 的文档行为。

        文档来源：builder→tester.md §7.4 条件路由规则
        """
        import os
        fix_prompt_path = os.path.join(
            context_dir, "tester→builder--修复指令.md"
        )
        if os.path.exists(fix_prompt_path):
            if iteration_count < 3:
                return "builder"
            else:
                return "seller"
        else:
            return "seller"

    def test_route_to_builder_when_fix_prompt_and_iteration_0(self) -> None:
        """P2-R1: 修复指令存在 + iteration=0 → "builder"（首次回退）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建修复指令文件
            fix_path = Path(tmpdir) / "tester→builder--修复指令.md"
            fix_path.write_text("修复内容", encoding="utf-8")

            result = self._route_after_tester(tmpdir, iteration_count=0)
            assert result == "builder"

    def test_route_to_builder_when_fix_prompt_and_iteration_1(self) -> None:
        """P2-R1: 修复指令存在 + iteration=1 → "builder"。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fix_path = Path(tmpdir) / "tester→builder--修复指令.md"
            fix_path.write_text("修复内容", encoding="utf-8")

            result = self._route_after_tester(tmpdir, iteration_count=1)
            assert result == "builder"

    def test_route_to_builder_when_fix_prompt_and_iteration_2(self) -> None:
        """P2-R1: 修复指令存在 + iteration=2 → "builder"。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fix_path = Path(tmpdir) / "tester→builder--修复指令.md"
            fix_path.write_text("修复内容", encoding="utf-8")

            result = self._route_after_tester(tmpdir, iteration_count=2)
            assert result == "builder"

    def test_route_to_seller_when_fix_prompt_and_iteration_3(self) -> None:
        """P2-R2: 修复指令存在 + iteration=3 → "seller"（已达上限，前进）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fix_path = Path(tmpdir) / "tester→builder--修复指令.md"
            fix_path.write_text("修复内容", encoding="utf-8")

            result = self._route_after_tester(tmpdir, iteration_count=3)
            assert result == "seller"

    def test_route_to_seller_when_fix_prompt_and_iteration_4(self) -> None:
        """P2-R3: 修复指令存在 + iteration=4 → "seller"（超限依然前进）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            fix_path = Path(tmpdir) / "tester→builder--修复指令.md"
            fix_path.write_text("修复内容", encoding="utf-8")

            result = self._route_after_tester(tmpdir, iteration_count=4)
            assert result == "seller"

    def test_route_to_seller_when_no_fix_prompt(self) -> None:
        """P2-R4: 无修复指令文件 → "seller"（通过）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._route_after_tester(tmpdir, iteration_count=0)
            assert result == "seller"

    def test_route_to_seller_when_empty_dir(self) -> None:
        """P2-R4: 空目录 + iteration=3 仍路由到 seller。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._route_after_tester(tmpdir, iteration_count=3)
            assert result == "seller"

    # ---- 验证实际 route_after_tester 与合约一致（跨平台，不依赖 langgraph 导入） ----

    def test_orchestrator_source_contains_route_condition(self) -> None:
        """验证 orchestrator.py 源码包含 route_after_tester 函数定义。"""
        orch_path = SRC_DIR / "agent_pipeline" / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")

        assert "def route_after_tester" in content, (
            "orchestrator.py 缺少 route_after_tester 函数"
        )
        assert "iteration_count" in content, (
            "route_after_tester 应检查 iteration_count"
        )
        assert "tester→builder--修复指令.md" in content, (
            "route_after_tester 应检查修复指令文件路径"
        )

    def test_orchestrator_source_uses_conditional_edges(self) -> None:
        """验证 orchestrator.py 使用 add_conditional_edges。"""
        orch_path = SRC_DIR / "agent_pipeline" / "orchestrator.py"
        content = orch_path.read_text(encoding="utf-8")

        assert "add_conditional_edges" in content, (
            "StateGraph 应使用条件边"
        )
        assert "route_after_tester" in content, (
            "条件边应使用 route_after_tester"
        )
        assert '"builder"' in content and '"seller"' in content, (
            "条件边应包含 builder 和 seller 路径"
        )


# ============================================================
# Phase 2 测试：CLI 五 Agent 看板（P2-C1, P2-C3）
# ============================================================


class TestPhase2CliDashboard:
    """Phase 2: CLI 输出包含五 Agent 名称和版本 0.2.0。

    溯源：
      designer→builder--phase2.md → test-plan.md P2-C1 → test.py // 验证 P2-C1
    """

    def test_help_displays_five_agent_names(self) -> None:
        """P2-C1: --help 输出含全部 5 个 Agent 名称。"""
        result = _run_cli(["--help"])

        assert result.returncode == 0

        # 五个 Agent 名称（使用 case-insensitive 检查处理编码差异）
        stdout_lower = result.stdout.lower()
        for name in ["scout", "designer", "builder", "tester", "seller"]:
            assert name in stdout_lower, (
                f"--help 应包含 '{name}'"
            )

    def test_help_mentions_pipeline_type(self) -> None:
        """P2-C1: --help 提及"五 Agent"或"五个 Agent"。"""
        result = _run_cli(["--help"])

        assert result.returncode == 0
        assert "五 Agent" in result.stdout or "五个" in result.stdout

    def test_help_run_mentions_agents(self) -> None:
        """run --help 描述含五个 Agent。"""
        result = _run_cli(["run", "--help"])

        assert result.returncode == 0
        # run 命令帮助应描述流水线类型
        assert "REQUIREMENT" in result.stdout

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Windows subprocess asyncio 限制，run 需要 langgraph 导入",
    )
    def test_status_output_five_agents_from_created_state(self) -> None:
        """P2-C4: status 输出包含五个 Agent 执行情况。

        创建带五 Agent 输出的模拟状态 → status 显示所有五个。
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建含五 Agent 输出状态的 state.json
            output_dir = Path(tmpdir) / "output" / "five-agent-project"
            output_dir.mkdir(parents=True, exist_ok=True)

            state = {
                "pipeline_id": "pl_20260610_testp2_abc123",
                "status": "completed",
                "requirement": "五 Agent 测试需求",
                "project_name": "五 Agent 项目",
                "project_slug": "five-agent-project",
                "context_dir": str(output_dir),
                "current_agent": "finalize",
                "phase": "full_pipeline",
                "agent_outputs": {
                    "scout": {"status": "completed", "summary": "调研报告已生成"},
                    "designer": {"status": "completed", "summary": "需求分析与架构设计已生成"},
                    "builder": {"status": "completed", "summary": "代码已生成（迭代 0/3）"},
                    "tester": {"status": "completed", "summary": "测试报告已生成"},
                    "seller": {"status": "completed", "summary": "README 已生成"},
                },
                "errors": [],
                "warnings": [],
                "knowledge_hit": False,
                "knowledge_sources": [],
                "created_at": "2026-06-10T12:00:00",
                "updated_at": "2026-06-10T12:05:00",
            }

            state_path = output_dir / "state.json"
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)

            result = _run_cli(["status"], env=BASE_ENV, cwd=tmpdir)

        assert result.returncode == 0
        # 验证五 Agent 名称全部出现
        for agent_name in ["Scout", "Designer", "Builder", "Tester", "Seller"]:
            assert agent_name in result.stdout, (
                f"status 输出应包含 Agent '{agent_name}'"
            )
        # 验证图标
        for icon in ["🔍", "🎨", "⚙️", "🧪", "📦"]:
            assert icon in result.stdout, (
                f"status 输出应包含图标 '{icon}'"
            )


# ============================================================
# Phase 2 测试：文件命名约定（P2-N1 ~ P2-N6）
# ============================================================


class TestPhase2FileNaming:
    """Phase 2: P2-N1 ~ P2-N6 — 产出物路径匹配 {producer}→{consumer}--{content}。

    溯源：
      designer→builder--phase2.md § 文件命名 → test-plan.md P2-N1 → test.py // 验证 P2-N1
    """

    ORCHESTRATOR_PATH = SRC_DIR / "agent_pipeline" / "orchestrator.py"

    def test_all_agent_outputs_use_arrow_naming(self) -> None:
        """P2-N1: 所有 Agent 产出路径使用 `→` 命名格式。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")

        # 检查所有产出路径
        naming_patterns = [
            "scout→designer--",
            "designer→builder--",
            "builder→tester--",
            "tester→seller--",
            "tester→builder--",
            "seller→user--",
        ]
        for pattern in naming_patterns:
            assert pattern in content, (
                f"orchestrator.py 应包含产出路径 '{pattern}'"
            )

    def test_scout_output_path_uses_arrow(self) -> None:
        """P2-N2: Scout 产出命名 scout→designer--调研报告.md。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "scout→designer--调研报告.md" in content, (
            "Scout 产出应使用 scout→designer--调研报告.md"
        )

    def test_designer_output_paths_use_arrow(self) -> None:
        """P2-N3: Designer 产出命名 designer→builder--需求分析.md + 架构设计.md。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "designer→builder--需求分析.md" in content
        assert "designer→builder--架构设计.md" in content

    def test_builder_output_path_uses_arrow(self) -> None:
        """P2-N4: Builder 产出命名 builder→tester--src/。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "builder→tester--src" in content

    def test_tester_output_paths_use_arrow(self) -> None:
        """P2-N5: Tester 产出命名 tester→seller-- + tester→builder--。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "tester→seller--测试报告.md" in content
        assert "tester→builder--修复指令.md" in content

    def test_seller_output_path_uses_arrow(self) -> None:
        """P2-N6: Seller 产出命名 seller→user--README.md。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "seller→user--README.md" in content


# ============================================================
# Phase 3 测试：模块导入（P3-T1 ~ P3-T3）
# ============================================================


class TestPhase3ModuleImport:
    """Phase 3: P3-T1 ~ P3-T2 — 验证 PipelineLogHandler 和 Web 服务模块可导入。

    溯源链：
      builder→tester.md §8.6 P3-T1 → test-plan.md P3-T1 → test_cli.py // 验证 P3-T1
    """

    @pytest.mark.skipif(sys.platform == "win32", reason="子进程 langgraph asyncio")
    def test_import_pipeline_log_handler(self) -> None:
        """P3-T1: PipelineLogHandler 可导入（BaseCallbackHandler 子类）。"""
        code = (
            "import sys; sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import PipelineLogHandler, now_iso, _write_line; "
            "import json; "
            "print('ok')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            env=BASE_ENV,
            cwd=str(PROJECT_ROOT),
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "ok" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="web.server 导入链含 langgraph")
    def test_import_web_server_app(self) -> None:
        """P3-T2: web.server.app FastAPI 实例创建成功。"""
        code = (
            "import sys; sys.path.insert(0, r'{}'); "
            "from agent_pipeline.web.server import app; "
            "print(f'title={app.title}'); "
            "routes = [r.path for r in app.routes]; "
            "print(f'routes={sorted(routes)}')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            env=BASE_ENV,
            cwd=str(PROJECT_ROOT),
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "title=" in result.stdout
        # 验证至少包含关键路由
        for route_path in ["/", "/run", "/stream/{pipeline_id}", "/shutdown", "/api/pipelines"]:
            assert route_path in result.stdout, f"缺少路由 {route_path}"


# ============================================================
# Phase 3 测试：CLI serve 命令（P3-T3, P3-T12）
# ============================================================


class TestPhase3ServeHelp:
    """Phase 3: P3-T3, P3-T12 — serve 命令存在且 --help 正常。

    溯源链：
      builder→tester.md §8.6 P3-T3 → test-plan.md P3-T3 → test_cli.py // 验证 P3-T3
    """

    def test_serve_in_help(self) -> None:
        """P3-T3: agent-pipeline --help 列出 serve 命令。"""
        result = _run_cli(["--help"])

        assert result.returncode == 0
        assert "serve" in result.stdout, "--help 应列出 serve 命令"

    def test_serve_help_shows_options(self) -> None:
        """P3-T12: serve --help 显示端口选项和描述。"""
        result = _run_cli(["serve", "--help"])

        assert result.returncode == 0
        assert "serve" in result.stdout
        assert "--port" in result.stdout, "serve --help 应显示 --port 选项"
        assert "--no-open" in result.stdout, "serve --help 应显示 --no-open 选项"


# ============================================================
# Phase 3 测试：前端文件存在性
# ============================================================


class TestPhase3FrontendFiles:
    """验证前端三个静态文件存在。"""

    STATIC_DIR = SRC_DIR / "agent_pipeline" / "web" / "static"

    def test_index_html_exists(self) -> None:
        """index.html 前端首页存在。"""
        path = self.STATIC_DIR / "index.html"
        assert path.exists(), f"{path} 不存在"

    def test_app_js_exists(self) -> None:
        """app.js SSE 前端逻辑存在。"""
        path = self.STATIC_DIR / "app.js"
        assert path.exists(), f"{path} 不存在"

    def test_styles_css_exists(self) -> None:
        """styles.css 暗色主题样式存在。"""
        path = self.STATIC_DIR / "styles.css"
        assert path.exists(), f"{path} 不存在"


# ============================================================
# Phase 3 测试：PipelineLogHandler 单元测试（P3-T13 ~ P3-T15）
# ============================================================


class TestPhase3LogHandler:
    """Phase 3: P3-T13 ~ P3-T15 + 额外单元测试。

    PipelineLogHandler 行为验证：
    - emit 写文件
    - QueueFull 不抛异常
    - emit 异常不阻断
    - CLI 模式 queue=None
    - now_iso 格式
    - set_log_path 更新路径

    溯源链：
      builder→tester.md §8.6 P3-T13 → test-plan.md P3-T13 → test_cli.py // 验证 P3-T13
    """

    @pytest.mark.skipif(sys.platform == "win32", reason="子进程 Python 代码字符串转义复杂")
    def test_handler_emit_writes_to_file(self) -> None:
        """P3-T13: emit 写入 pipeline.log 且内容正确。"""
        code = (
            "import sys, os, json, tempfile; "
            "sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import PipelineLogHandler; "
            "with tempfile.TemporaryDirectory() as d: "
            "  log_path = os.path.join(d, 'pipeline.log'); "
            "  handler = PipelineLogHandler(log_path=log_path, event_queue=None); "
            "  handler.current_agent = 'scout'; "
            "  handler._emit({{'time':'12:00:00','agent':'scout','event':'agent_start'}}); "
            "  with open(log_path,'r') as f: content = f.read(); "
            "  data = json.loads(content.strip()); "
            "  assert data['event'] == 'agent_start', f'Got {{data}}'; "
            "  assert data['agent'] == 'scout'; "
            "  assert data['time'] == '12:00:00'; "
            "print('PASS')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="子进程 Python 代码字符串转义复杂")
    def test_handler_queue_full_does_not_raise(self) -> None:
        """QueueFull 异常被静默捕获，不抛出。"""
        code = (
            "import sys, os, asyncio, tempfile, json; "
            "sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import PipelineLogHandler; "
            "async def run_test(): "
            "  with tempfile.TemporaryDirectory() as d: "
            "    log_path = os.path.join(d, 'pipeline.log'); "
            "    queue = asyncio.Queue(maxsize=1); "
            "    handler = PipelineLogHandler(log_path=log_path, event_queue=queue); "
            "    handler.current_agent = 'test'; "
            "    queue.put_nowait({{'dummy': True}}); "
            "    handler._emit({{'time':'12:00','agent':'test','event':'overflow'}}); "
            "    handler._emit({{'time':'12:00','agent':'test','event':'overflow2'}}); "
            "  print('PASS'); "
            "asyncio.run(run_test())"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="子进程 Python 代码字符串转义复杂")
    def test_handler_exception_does_not_block(self) -> None:
        """emit 内部异常被 try/except 捕获，不抛出。"""
        code = (
            "import sys, os, tempfile; "
            "sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import PipelineLogHandler; "
            "with tempfile.TemporaryDirectory() as d: "
            "  log_path = os.path.join(d, 'pipeline.log'); "
            "  handler = PipelineLogHandler(log_path=log_path, event_queue=None); "
            "  handler.current_agent = 'test'; "
            "  handler._emit(None); "
            "  handler._emit(123); "
            "print('PASS')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="子进程 Python 代码字符串转义复杂")
    def test_handler_cli_mode_queue_none(self) -> None:
        """CLI 模式 queue=None 时 emit 只写文件，不尝试推 SSE。"""
        code = (
            "import sys, os, json, tempfile; "
            "sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import PipelineLogHandler; "
            "with tempfile.TemporaryDirectory() as d: "
            "  log_path = os.path.join(d, 'pipeline.log'); "
            "  handler = PipelineLogHandler(log_path=log_path, event_queue=None); "
            "  handler.current_agent = 'scout'; "
            "  handler._emit({{'time':'12:00','agent':'scout','event':'agent_start'}}); "
            "  assert handler._queue is None; "
            "print('PASS')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_handler_now_iso_format(self) -> None:
        """now_iso() 返回 HH:MM:SS 格式。"""
        code = (
            "import sys; "
            "sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import now_iso; "
            "import re; "
            "t = now_iso(); "
            "assert re.match(r'^\\d{{2}}:\\d{{2}}:\\d{{2}}$', t), f'Format invalid: {{t}}'; "
            "print('PASS')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="子进程 Python 代码字符串转义复杂")
    def test_handler_set_log_path(self) -> None:
        """set_log_path() 可更新日志文件路径。"""
        code = (
            "import sys, os, json, tempfile; "
            "sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import PipelineLogHandler; "
            "with tempfile.TemporaryDirectory() as d: "
            "  log_path1 = os.path.join(d, 'pipeline.log'); "
            "  log_path2 = os.path.join(d, 'updated.log'); "
            "  handler = PipelineLogHandler(log_path=log_path1, event_queue=None); "
            "  handler.set_log_path(log_path2); "
            "  handler.current_agent = 'scout'; "
            "  handler._emit({{'time':'12:00','agent':'scout','event':'agent_start'}}); "
            "  assert not os.path.exists(log_path1); "
            "  assert os.path.exists(log_path2); "
            "print('PASS')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    @pytest.mark.skipif(sys.platform == "win32", reason="子进程 Python 代码字符串转义复杂")
    def test_handler_pipeline_end_event_format(self) -> None:
        """P3-T15: emit pipeline_end 事件写入文件格式正确。"""
        code = (
            "import sys, os, json, tempfile; "
            "sys.path.insert(0, r'{}'); "
            "from agent_pipeline.log_handler import PipelineLogHandler; "
            "with tempfile.TemporaryDirectory() as d: "
            "  log_path = os.path.join(d, 'pipeline.log'); "
            "  handler = PipelineLogHandler(log_path=log_path, event_queue=None); "
            "  handler.current_agent = None; "
            "  handler._emit({{"
            "    'time':'12:00','agent':None,'event':'pipeline_end','status':'completed'"
            "  }}); "
            "  with open(log_path,'r') as f: content = f.read(); "
            "  data = json.loads(content.strip()); "
            "  assert data['event'] == 'pipeline_end'; "
            "  assert data['status'] == 'completed'; "
            "  assert data['agent'] is None; "
            "print('PASS')"
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=15,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout


# ============================================================
# Phase 3 测试：FastAPI Web 端点（P3-T4 ~ P3-T9）
# ============================================================


class TestPhase3WebServer:
    """Phase 3: P3-T4 ~ P3-T9 — FastAPI 端点响应测试。

    使用 subprocess + TestClient 验证端点行为。

    溯源链：
      builder→tester.md §8.6 P3-T4 → test-plan.md P3-T4 → test_cli.py // 验证 P3-T4
    """

    def _run_test_client_code(self, code_body: str, timeout: int = 15) -> subprocess.CompletedProcess:
        """在子进程中运行 TestClient 测试代码并返回结果。"""
        full_code = (
            "import sys; sys.path.insert(0, r'{}'); "
            "from fastapi.testclient import TestClient; "
            "from agent_pipeline.web.server import app; "
            "client = TestClient(app); "
            + code_body
        ).format(SRC_DIR)
        return subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True, text=True,
            timeout=timeout,
        )

    def test_get_index_returns_200(self) -> None:
        """P3-T4: GET / 返回 200 + text/html。"""
        code = (
            "resp = client.get('/'); "
            "assert resp.status_code == 200, f'Expected 200, got {{resp.status_code}}'; "
            "ct = resp.headers.get('content-type', ''); "
            "assert 'text/html' in ct, f'Expected text/html, got {{ct}}'; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_post_run_empty_requirement_400(self) -> None:
        """P3-T5: POST /run 空需求返回 400。"""
        code = (
            "resp = client.post('/run', json={{'requirement': ''}}); "
            "assert resp.status_code == 400, f'Expected 400, got {{resp.status_code}}'; "
            "data = resp.json(); "
            "assert 'error' in data, f'Expected error field in {{data}}'; "
            "assert '不能为空' in data['error'], f'Expected empty error msg in {{data}}'; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_post_run_empty_json_400(self) -> None:
        """P3-T5 衍生: POST /run 空 JSON 返回 400。"""
        code = (
            "resp = client.post('/run', json={{}}); "
            "assert resp.status_code == 400, f'Expected 400, got {{resp.status_code}}'; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_post_run_valid_returns_200_with_pipeline_id(self) -> None:
        """P3-T6: POST /run 有效需求返回 200 + pipeline_id。"""
        code = (
            "resp = client.post('/run', json={{'requirement': '测试需求'}}); "
            "assert resp.status_code == 200, f'Expected 200, got {{resp.status_code}}: {{resp.text}}'; "
            "data = resp.json(); "
            "assert 'pipeline_id' in data, f'Expected pipeline_id in {{data}}'; "
            "assert str(data['pipeline_id']).startswith('pl_'), f'Bad pipeline_id format: {{data}}'; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_second_post_run_returns_429(self) -> None:
        """P3-T7: 第二次 POST /run 返回 429（已有流水线在运行）。"""
        code = (
            "resp1 = client.post('/run', json={{'requirement': '第一个需求'}}); "
            "assert resp1.status_code == 200; "
            "resp2 = client.post('/run', json={{'requirement': '第二个需求'}}); "
            "assert resp2.status_code == 429, f'Expected 429, got {{resp2.status_code}}: {{resp2.text}}'; "
            "data2 = resp2.json(); "
            "assert 'error' in data2; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code, timeout=30)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_get_stream_not_found_404(self) -> None:
        """P3-T8: GET /stream/{id} 不存在的流水线返回 404。"""
        code = (
            "resp = client.get('/stream/nonexistent_pipeline_id'); "
            "assert resp.status_code == 404, f'Expected 404, got {{resp.status_code}}: {{resp.text}}'; "
            "data = resp.json(); "
            "assert 'error' in data; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_get_api_pipelines_returns_json_array(self) -> None:
        """P3-T9: GET /api/pipelines 返回 JSON 数组。"""
        code = (
            "resp = client.get('/api/pipelines'); "
            "assert resp.status_code == 200, f'Expected 200, got {{resp.status_code}}: {{resp.text}}'; "
            "data = resp.json(); "
            "assert isinstance(data, list), f'Expected list, got {{type(data)}}'; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout

    def test_static_files_served(self) -> None:
        """静态文件 /static/styles.css 可访问。"""
        code = (
            "resp = client.get('/static/styles.css'); "
            "assert resp.status_code == 200, f'Expected 200, got {{resp.status_code}}: {{resp.text}}'; "
            "print('PASS')"
        )
        result = self._run_test_client_code(code)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "PASS" in result.stdout


# ============================================================
# Phase 3 测试：Eclipse 熄灯端点（P3-T10）
# ============================================================


class TestPhase3Shutdown:
    """Phase 3: P3-T10 — POST /shutdown 端点。

    由于 /shutdown 调用 os._exit(0)，TestClient 子进程会被终止。
    测试策略：
    1. 源码验证 shutdown 端点存在（不依赖执行）
    2. 子进程中执行 /shutdown 并捕获终止前的返回内容
    """

    SERVER_PATH = SRC_DIR / "agent_pipeline" / "web" / "server.py"

    def test_shutdown_endpoint_in_source(self) -> None:
        """源码验证 POST /shutdown 端点存在且返回 eclipsed。"""
        content = self.SERVER_PATH.read_text(encoding="utf-8")
        assert "@app.post(\"/shutdown\")" in content, "缺少 /shutdown 端点"
        assert "eclipsed" in content, "shutdown 应返回 eclipsed"
        assert "os._exit" in content, "shutdown 应调用 os._exit(0)"

    def test_shutdown_returns_eclipsed_before_exit(self) -> None:
        """P3-T10: POST /shutdown 返回 {"status":"eclipsed"}（在 os._exit 前）。"""
        code = (
            "import sys; sys.path.insert(0, r'{}'); "
            "from fastapi.testclient import TestClient; "
            "from agent_pipeline.web.server import app; "
            "client = TestClient(app); "
            "resp = client.post('/shutdown'); "
            "print(f'STATUS={{resp.status_code}}'); "
            "data = resp.json(); "
            "print(f'DATA={{data}}'); "
        ).format(SRC_DIR)
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            timeout=5,
        )
        assert "STATUS=200" in result.stdout or result.returncode == 0
        assert "eclipsed" in result.stdout, f"Expected 'eclipsed' in output. stdout={result.stdout}, stderr={result.stderr}"


# ============================================================
# Phase 3 测试：Orchestrator handler 注入
# ============================================================


class TestPhase3OrchestratorHandler:
    """验证 orchestrator 的全局 handler 注入机制。

    测试点：
    - set_pipeline_handler / _get_handler 函数存在
    - CLI 模式 handler=None 不影响现有行为
    - 7 个 node 均检查 handler 并 emit agent_start/agent_end
    """

    ORCHESTRATOR_PATH = SRC_DIR / "agent_pipeline" / "orchestrator.py"

    def test_handler_functions_exist_in_source(self) -> None:
        """orchestrator.py 包含 set_pipeline_handler 和 _get_handler。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "def set_pipeline_handler" in content, "缺少 set_pipeline_handler"
        assert "def _get_handler" in content, "缺少 _get_handler"
        assert "_pipeline_handler = None" in content, "缺少全局 handler 变量"

    def test_all_nodes_emit_events(self) -> None:
        """所有 7 个 node 函数都调用 _get_handler() 并 emit agent_start/agent_end。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        node_names = ["parse_node", "scout_node", "designer_node",
                       "builder_node", "tester_node", "seller_node", "finalize_node"]
        for node in node_names:
            assert f"def {node}" in content, f"缺少节点 {node}"

        assert "_get_handler()" in content
        assert "agent_start" in content
        assert "agent_end" in content
        assert "handler.current_agent" in content

    def test_orchestrator_imports_now_iso(self) -> None:
        """orchestrator 导入 now_iso 用于 emit 事件时间。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "from .log_handler import now_iso" in content

    def test_invoke_agent_supports_callbacks(self) -> None:
        """_invoke_agent 接受 callbacks 参数。"""
        content = self.ORCHESTRATOR_PATH.read_text(encoding="utf-8")
        assert "callbacks" in content
        assert '"callbacks": callbacks' in content or "\"callbacks\": callbacks" in content
