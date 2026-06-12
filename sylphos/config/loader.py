from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _import_optional_module(module_name: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_name)
    except Exception:
        return None


def _load_python_file(path: Path, module_name: str) -> ModuleType | None:
    """Load an optional config file by path without requiring it to be importable."""

    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    return module


def load_config() -> SimpleNamespace:
    data: dict[str, Any] = {}
    defaults = importlib.import_module("sylphos.config.defaults")
    data.update(_public_attrs(defaults))

    repo_root = _repo_root()
    module_sources: list[ModuleType | None] = [
        _import_optional_module("config"),
        _import_optional_module("sylphos.config.settings"),
        # Also support .\config\local_config.py (Windows) / ./config/local_config.py
        # (Linux/macOS). Loading by path keeps this working even when the repo
        # root is not importable as a package in the current Python session.
        _import_optional_module("config.local_config")
        or _load_python_file(repo_root / "config" / "local_config.py", "sylphos_config_local_config"),
        # Root-level local_config.py remains the preferred legacy override
        # location, so it is applied after config/local_config.py.
        _import_optional_module("local_config") or _load_python_file(repo_root / "local_config.py", "sylphos_root_local_config"),
        _import_optional_module("sylphos.config.local_config"),
    ]
    for module in module_sources:
        if module is not None:
            data.update(_public_attrs(module))

    # Environment variables have the highest priority and keep the existing
    # coercion behavior based on the current default/local value type.
    for name, current in list(data.items()):
        if name in os.environ:
            data[name] = _coerce_env(os.environ[name], current)
    return SimpleNamespace(**data)
