"""Deterministic synthetic workforce data for CareStaff Insight."""

from data_generation.config import load_config
from data_generation.engine import generate_tables

__all__ = ["load_config", "generate_tables"]
