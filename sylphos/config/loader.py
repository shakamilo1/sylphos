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


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    for root in (Path.cwd(), _repo_root()):
        resolved = root.resolve()
        if resolved not in roots:
            roots.append(resolved)
    return roots


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
    """Load an optional config file by path without requiring sys.path edits."""

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


def _apply_module(data: dict[str, Any], module: ModuleType | None) -> None:
    if module is not None:
        data.update(_public_attrs(module))


def load_config() -> SimpleNamespace:
    data: dict[str, Any] = {}

    # 1. Defaults are always the base layer.
    defaults = importlib.import_module("sylphos.config.defaults")
    data.update(_public_attrs(defaults))

    roots = _candidate_roots()

    # 2. Existing root-level local_config.py override. Loaded by file path so
    # users do not need to manually add the project root to sys.path.
    _apply_module(data, _load_first_existing_file((root / "local_config.py" for root in roots), "sylphos_root_local_config"))

    # 3. Existing package-local sylphos/config/local_config.py override.
    _apply_module(data, _import_optional_module("sylphos.config.local_config"))

    # 4. New project-root config/local_config.py override.  This supports both
    # Windows .\config\local_config.py and Linux/macOS ./config/local_config.py
    # without copying the file to the root or modifying sys.path.
    _apply_module(
        data,
        _load_first_existing_file(
            (root / "config" / "local_config.py" for root in roots),
            "sylphos_project_config_local_config",
        ),
    )

    # 5. Environment variables have the highest priority and keep the existing
    # coercion behavior based on the current default/local value type.
    for name, current in list(data.items()):
        if name in os.environ:
            data[name] = _coerce_env(os.environ[name], current)
    return SimpleNamespace(**data)
