# sylphos/__init__.py
import sys

__all__ = ["__version__"]
__version__ = "0.1.0"

_MIN_VERSION = (3, 13)

if sys.version_info < _MIN_VERSION:
    v = ".".join(map(str, _MIN_VERSION))
    raise RuntimeError(
        f"Sylphos requires Python >= {v}, "
        f"but you are running {sys.version.split()[0]}"
    )
