from __future__ import annotations

import importlib
import importlib.util
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Iterable


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
        spec = importlib.util.find_spec(module_name)
    except (ImportError, AttributeError, ValueError):
        spec = None
    if spec is None:
        return None
    try:
        return importlib.import_module(module_name)
    except Exception as exc:
        raise RuntimeError(f"Failed to import optional config module {module_name!r}: {exc}") from exc


def _load_python_file(path: Path, module_name: str) -> ModuleType | None:
    """Load an optional config file by path without requiring it to be importable."""

    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to create import spec for config file: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise RuntimeError(f"Failed to load config file {path}: {exc}") from exc
    return module


def _load_first_existing_file(paths: Iterable[Path], module_name: str) -> ModuleType | None:
    for path in paths:
        module = _load_python_file(path, module_name)
        if module is not None:
            return module
    return None


def load_config() -> SimpleNamespace:
    data: dict[str, Any] = {}
    defaults = importlib.import_module("sylphos.config.defaults")
    data.update(_public_attrs(defaults))

    cwd = Path.cwd()
    repo_root = _repo_root()
    root_candidates = [cwd]
    if repo_root != cwd:
        root_candidates.append(repo_root)

    module_sources: list[ModuleType | None] = [
        # 1. sylphos.config.defaults is loaded above.
        # 2. Project-root config.py, loaded by path so it is not confused with
        #    the config/ package directory.
        _load_first_existing_file((root / "config.py" for root in root_candidates), "sylphos_root_config"),
        # 3. Package-level settings.
        _import_optional_module("sylphos.config.settings"),
        # 4. Project-root local_config.py, preserving the existing override path.
        _load_first_existing_file((root / "local_config.py" for root in root_candidates), "sylphos_root_local_config"),
        # 5. Package-local sylphos/config/local_config.py.
        _import_optional_module("sylphos.config.local_config"),
        # 6. Project-root .\config\local_config.py (Windows) /
        #    ./config/local_config.py (Linux/macOS).  This is loaded by path so
        #    users do not need to copy it to the root or manually edit sys.path.
        _load_first_existing_file(
            (root / "config" / "local_config.py" for root in root_candidates),
            "sylphos_project_config_local_config",
        ),
    ]
    for module in module_sources:
        if module is not None:
            data.update(_public_attrs(module))

    # 7. Environment variables have the highest priority and keep the existing
    # coercion behavior based on the current default/local value type.
    for name, current in list(data.items()):
        if name in os.environ:
            data[name] = _coerce_env(os.environ[name], current)
    return SimpleNamespace(**data)
