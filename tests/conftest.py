from __future__ import annotations

from pathlib import Path

import pytest

from data_generation.config import load_config
from data_generation.engine import generate_tables

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"


@pytest.fixture(scope="session")
def seed_cfg():
    return load_config("seed")


@pytest.fixture(scope="session")
def seed_tables(seed_cfg):
    return generate_tables(seed_cfg)
