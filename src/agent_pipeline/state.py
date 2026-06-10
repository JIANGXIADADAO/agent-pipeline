"""状态持久化 — state.json 的读写和流水线历史管理。"""

import json
import os
from pathlib import Path
from typing import Optional

from .models import PipelineState

# 流水线产出根目录（相对于项目根目录）
OUTPUT_DIR = "output"


def _ensure_output_dir(context_dir: str) -> Path:
    """确保上下文目录存在并返回 Path 对象。"""
    path = Path(context_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_state(state: PipelineState) -> None:
    """将流水线状态写入 {context_dir}/state.json。"""
    if not state.context_dir:
        raise ValueError("PipelineState.context_dir 为空，无法保存状态")

    path = _ensure_output_dir(state.context_dir) / "state.json"
    data = state.to_dict()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_state(context_dir: str) -> Optional[PipelineState]:
    """从 {context_dir}/state.json 读取流水线状态。"""
    path = Path(context_dir) / "state.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return PipelineState.from_dict(data)
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"state.json 解析失败: {e}")


def load_latest_state() -> Optional[PipelineState]:
    """从 output/ 中找到最近更新的流水线状态。"""
    output_dir = Path(OUTPUT_DIR)
    if not output_dir.exists():
        return None

    # 扫描 output/*/state.json，按 mtime 排序取最新
    candidates = []
    for project_dir in output_dir.iterdir():
        if project_dir.is_dir():
            state_file = project_dir / "state.json"
            if state_file.exists():
                candidates.append(state_file)

    if not candidates:
        return None

    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return load_state(str(latest.parent))


def list_pipelines(limit: int = 20) -> list[PipelineState]:
    """列出最近完成的流水线。"""
    output_dir = Path(OUTPUT_DIR)
    if not output_dir.exists():
        return []

    pipelines = []
    for project_dir in output_dir.iterdir():
        if project_dir.is_dir():
            state_file = project_dir / "state.json"
            if state_file.exists():
                try:
                    state = load_state(str(project_dir))
                    if state:
                        pipelines.append(state)
                except ValueError:
                    pass  # 跳过损坏的 state.json

    # 按 created_at 降序排列
    pipelines.sort(key=lambda s: s.created_at, reverse=True)
    return pipelines[:limit]
