"""Gold features and operational KPIs."""

from __future__ import annotations

from typing import Any

__all__ = ["build_gold"]


def __getattr__(name: str) -> Any:
    if name == "build_gold":
        from src.gold.build import build_gold

        return build_gold
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
