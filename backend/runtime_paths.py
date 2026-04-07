from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_root() -> Path:
    explicit = os.environ.get("KAM_BUNDLE_ROOT")
    if explicit:
        return Path(explicit).resolve()
    if is_frozen_runtime() and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parents[1]


def runtime_root() -> Path:
    explicit = os.environ.get("KAM_RUNTIME_ROOT")
    if explicit:
        return Path(explicit).resolve()
    if is_frozen_runtime():
        return Path(sys.executable).resolve().parent
    return bundle_root()


def bundled_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


def runtime_path(*parts: str) -> Path:
    return runtime_root().joinpath(*parts)
