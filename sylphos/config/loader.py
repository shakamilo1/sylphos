from __future__ import annotations

import importlib
import os
from types import SimpleNamespace
from typing import Any


def _public_attrs(module: Any) -> dict[str, Any]:
    return {name: getattr(module, name) for name in dir(module) if name.isupper()}


def _coerce_env(value: str, current: Any) -> Any:
    if current is None:
        return None if value == "" or value.lower() == "none" else value
    if isinstance(current, bool):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return value


def load_config() -> SimpleNamespace:
    data: dict[str, Any] = {}
    defaults = importlib.import_module("sylphos.config.defaults")
    data.update(_public_attrs(defaults))
    for module_name in ("config", "sylphos.config.settings", "local_config", "sylphos.config.local_config"):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        data.update(_public_attrs(module))
    for name, current in list(data.items()):
        if name in os.environ:
            data[name] = _coerce_env(os.environ[name], current)
    return SimpleNamespace(**data)
