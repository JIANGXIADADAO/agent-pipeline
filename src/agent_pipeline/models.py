"""数据模型 — PipelineState 和 AgentOutput 数据类。"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Literal


@dataclass
class AgentOutput:
    """单个 Agent 的执行输出。"""

    status: Literal["pending", "running", "completed", "failed"] = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    output_path: Optional[str] = None
    summary: str = ""
    raw_output: str = ""
    error: Optional[str] = None
    retry_count: int = 0
    artifacts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AgentOutput":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class PipelineState:
    """流水线完整状态。

    Phase 1 是直线流程：requirement → scout → completed。
    Phase 2+ 会扩展为多 Agent 多阶段。
    """

    requirement: str
    project_name: str = ""
    project_slug: str = ""
    current_agent: str = "scout"
    phase: str = "scout"
    agent_outputs: dict[str, AgentOutput] = field(default_factory=dict)
    status: str = "idle"  # idle | running | completed | failed
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    context_dir: str = ""
    knowledge_hit: bool = False
    knowledge_sources: list[str] = field(default_factory=list)
    pipeline_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["agent_outputs"] = {
            k: v.to_dict() for k, v in self.agent_outputs.items()
        }
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineState":
        agent_outputs = {}
        for k, v in data.get("agent_outputs", {}).items():
            agent_outputs[k] = AgentOutput.from_dict(v)
        filtered = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        filtered["agent_outputs"] = agent_outputs
        return cls(**filtered)
