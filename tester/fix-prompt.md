# Tester → Builder 修复指令

## Bug #1: `--version` 未实现 ⭐ 低

**测试**：`test_version_not_implemented`（通过但反向验证——确认了 --version 不支持）
**CLI 参考声明**：`agent-pipeline --version` 应显示版本号
**实际**：`cli/main.py` 没有 `@click.version_option`
**修复**：在 `cli()` 函数上加 `@click.version_option(version="0.1.0")`，导入 `from agent_pipeline import __version__`

---

## Bug #2: CLI 参考环境变量名错误 ⭐⭐ 中

**测试**：`test_no_api_key`（通过——验证了实际报错中的变量名）
**CLI 参考写的是**：`ANTHROPIC_API_KEY`
**实际代码使用**：`DEEPSEEK_API_KEY`
**影响**：新用户按文档设置会失败
**修复**：更新 `builder/cli-reference.md`，把所有 `ANTHROPIC_API_KEY` 改为 `DEEPSEEK_API_KEY`

---

## Bug #3: 启动输出时序错误 ⭐ 低

**测试**：`test_start_output_format`（通过——验证了启动格式正确，但时机不对）
**实际**：`_print_pipeline_start(state)` 在 `run_pipeline()` 返回后才调用，用户看到 "🚀 流水线已启动" 时流水线实际已经跑完了
**影响**：UX 问题，Phase 2 SSE 推送会根本解决
**修复（Phase 1）**：把 `_print_pipeline_start` 移到 `run_pipeline()` 调用之前

---

## 修复验证

修复后重新跑 `pytest src/tests/ -v`，确认 35 条仍全部通过。

---

## Bug #4: 5 条 Phase 1 测试在 Windows 缺少 skipif 标记 ⭐⭐ 中

**现象**：Windows 下 5 条测试失败，全部因为 `python -m agent_pipeline.cli.main run` 子进程触发 langgraph 导入链 → `import asyncio` → Windows `_overlapped` 崩溃。

**根因**：`langgraph.stream._types` 在子进程中触发 `import asyncio`，而 Windows `asyncio.windows_events` 无法在子进程加载 `_overlapped` 模块。`test_invalid_api_key_creates_state` 已正确标记了 `skipif(win32)`，但以下 5 条没有。

**受影响的测试**（均在 `src/tests/test_cli.py`）：

| 测试方法 | 类 | 原因 |
|---------|------|------|
| `test_invalid_api_key_run_fails_gracefully` | `TestRunErrors` | `python -m` run 触发 langgraph 导入 |
| `test_start_output_format` | `TestCliOutput` | 同上 |
| `test_failure_output_format` | `TestCliOutput` | 同上 |
| `test_failed_run_creates_state` | `TestStatePersistence` | 同上 — state.json 未被创建 |
| `test_status_after_failed_run` | `TestStatePersistence` | 同上 — run 崩溃后无 state.json |

**修复**：在 5 条测试方法前添加 `@pytest.mark.skipif` 装饰器：

```python
@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Windows subprocess asyncio 线程限制，run 命令需要 langgraph 导入",
)
```

**修复验证**：Windows 上 `pytest src/tests/test_cli.py -v` 零 Fail。
