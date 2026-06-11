from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any


def _public_attrs(module: Any) -> dict[str, Any]:
    return {name: getattr(module, name) for name in dir(module) if name.isupper()}


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
    return SimpleNamespace(**data)
