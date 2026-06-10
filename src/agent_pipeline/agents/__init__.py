"""Agent 模块 — 五个 ReAct Agent 的创建工厂。

Scout     — 市场调研（Phase 1 复用，输出路径微调）
Designer  — 产品设计（Phase 2 新增）
Builder   — 编码实现（Phase 2 新增）
Tester    — 质量验证（Phase 2 新增）
Seller    — 发布准备（Phase 2 新增）
"""

from .scout import create_scout_agent
from .designer import create_designer_agent
from .builder import create_builder_agent
from .tester import create_tester_agent
from .seller import create_seller_agent

__all__ = [
    "create_scout_agent",
    "create_designer_agent",
    "create_builder_agent",
    "create_tester_agent",
    "create_seller_agent",
]
