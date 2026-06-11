from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeRegistry:
    modules: dict[str, Any] = field(default_factory=dict)
    executors: dict[str, Any] = field(default_factory=dict)

    def register(self, name: str, module: Any) -> Any:
        self.modules[name] = module
        return module

    def get(self, name: str, default: Any = None) -> Any:
        return self.modules.get(name, default)

    def register_executor(self, name: str, executor: Any) -> Any:
        self.executors[name] = executor
        return executor

    def get_executor(self, name: str, default: Any = None) -> Any:
        return self.executors.get(name, default)

    def close_all(self) -> None:
        for module in list(self.modules.values()) + list(self.executors.values()):
            close = getattr(module, "close", None) or getattr(module, "stop", None)
            if callable(close):
                close()
