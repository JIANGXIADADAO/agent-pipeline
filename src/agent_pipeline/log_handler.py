"""PipelineLogHandler — LangChain 回调处理器。

同时写入 pipeline.log（持久化）和 asyncio.Queue（SSE 实时推）。
所有 emit 由 try/except 保护——日志失败不影响 pipeline 主流程。
"""

import json
import asyncio
from datetime import datetime
from typing import Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler


def _write_line(path: str, line: str):
    """追加写入日志行（线程安全，GIL 保护）。"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def now_iso() -> str:
    """返回 HH:MM:SS 格式的当前时间字符串。"""
    return datetime.now().strftime("%H:%M:%S")


class PipelineLogHandler(BaseCallbackHandler):
    """LangChain 回调 — 同时写入 pipeline.log 和 asyncio.Queue。

    属性:
        current_agent: orchestrator 在调用 agent.invoke 前设置
        _log_path: pipeline.log 文件路径
        _queue: asyncio.Queue（None = CLI 模式，不推 SSE）
        _tool_names: run_id → tool_name 映射，用于 on_tool_end 获取工具名
    """

    def __init__(self, log_path: str, event_queue: Optional[asyncio.Queue] = None):
        self._log_path = log_path
        self._queue = event_queue  # None = CLI 模式
        self.current_agent: Optional[str] = None
        self._tool_names: dict[str, str] = {}  # run_id -> tool name

    # ---- 公开方法 ----

    def set_log_path(self, path: str):
        """运行时更新日志文件路径（parse_node 确定 context_dir 后调用）。"""
        self._log_path = path

    # ---- 内部事件发射 ----

    def _emit(self, event: dict):
        """发射事件：写入 pipeline.log + 可选推入 SSE 队列。"""
        try:
            line = json.dumps(event, ensure_ascii=False) + "\n"
            _write_line(self._log_path, line)
            if self._queue:
                try:
                    self._queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # 队列满不阻塞
                except RuntimeError:
                    pass  # 事件循环未运行
        except Exception:
            pass  # 日志失败不影响 pipeline 主流程

    # ---- LangChain 回调 ----

    def on_chat_model_start(self, serialized: dict, messages: list, **kwargs):
        """聊天模型开始调用（ChatOpenAI 触发此回调）。"""
        if self.current_agent:
            self._emit({
                "time": now_iso(),
                "agent": self.current_agent,
                "event": "llm_start",
            })

    def on_chat_model_end(self, response, **kwargs):
        """聊天模型调用结束。"""
        if self.current_agent:
            self._emit({
                "time": now_iso(),
                "agent": self.current_agent,
                "event": "llm_end",
            })

    def on_llm_start(self, serialized: dict, prompts: list[str], **kwargs):
        """LLM 开始调用（兼容旧版 LLM）。"""
        if self.current_agent:
            self._emit({
                "time": now_iso(),
                "agent": self.current_agent,
                "event": "llm_start",
            })

    def on_llm_end(self, response, **kwargs):
        """LLM 调用结束。"""
        if self.current_agent:
            self._emit({
                "time": now_iso(),
                "agent": self.current_agent,
                "event": "llm_end",
            })

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs):
        """工具开始调用。"""
        run_id = str(kwargs.get("run_id", ""))
        tool_name = serialized.get("name", "unknown")
        if run_id:
            self._tool_names[run_id] = tool_name

        if self.current_agent:
            self._emit({
                "time": now_iso(),
                "agent": self.current_agent,
                "event": "tool_start",
                "tool": tool_name,
                "input": str(input_str)[:200],
            })

    def on_tool_end(self, output: str, **kwargs):
        """工具调用结束。"""
        run_id = str(kwargs.get("run_id", ""))
        tool_name = self._tool_names.pop(run_id, "unknown") if run_id else "unknown"

        if self.current_agent:
            self._emit({
                "time": now_iso(),
                "agent": self.current_agent,
                "event": "tool_end",
                "tool": tool_name,
            })
