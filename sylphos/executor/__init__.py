"""Executor bridge integrations for Sylphos."""

from .base import ToolExecutor
from .openclaw_bridge import SylphosOpenClawBridge, classify_risk
from .openclaw_config import OpenClawBridgeConfig, load_openclaw_bridge_config
from .openclaw_executor import (
    DummyExecutor,
    OpenClawApiExecutor,
    OpenClawCliExecutor,
    OpenClawExecutionError,
    OpenClawExecutor,
    OpenClawWebSocketExecutor,
)
from .openclaw_models import OpenClawRequest, OpenClawBridgeResult

__all__ = [
    "OpenClawBridgeConfig",
    "OpenClawRequest",
    "OpenClawBridgeResult",
    "SylphosOpenClawBridge",
    "ToolExecutor",
    "DummyExecutor",
    "OpenClawExecutionError",
    "OpenClawExecutor",
    "OpenClawCliExecutor",
    "OpenClawApiExecutor",
    "OpenClawWebSocketExecutor",
    "classify_risk",
    "load_openclaw_bridge_config",
]
