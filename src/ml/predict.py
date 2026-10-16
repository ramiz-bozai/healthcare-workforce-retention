"""In-process predict. This is not Model Serving."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.common.paths import MODEL_DIR
from src.ml.contract import (
    ATTRITION_CATEGORICAL,
    ATTRITION_NUMERIC,
    SHORTAGE_CATEGORICAL,
    SHORTAGE_NUMERIC,
)
from src.ml.features import feature_frame


@dataclass
class LocalModels:
    attrition: object
    shortage: object
    policy: dict
    model_dir: Path

    def predict_attrition(self, frame: pd.DataFrame) -> np.ndarray:
        X = feature_frame(frame, ATTRITION_NUMERIC, ATTRITION_CATEGORICAL)
        return self.attrition.predict_proba(X)[:, 1]

    def predict_shortage(self, frame: pd.DataFrame) -> np.ndarray:
        X = feature_frame(frame, SHORTAGE_NUMERIC, SHORTAGE_CATEGORICAL)
        return self.shortage.predict_proba(X)[:, 1]


def load_local_models(model_dir: Path | None = None) -> LocalModels:
    dest = Path(model_dir or MODEL_DIR)
    attrition_path = dest / "attrition.joblib"
    shortage_path = dest / "shortage.joblib"
    policy_path = dest / "policy.json"
    if not attrition_path.exists() or not shortage_path.exists():
        raise FileNotFoundError(f"Models missing in {dest}. Run `uv run python -m src.ml` first.")
    policy = json.loads(policy_path.read_text()) if policy_path.exists() else {}
    return LocalModels(
        attrition=joblib.load(attrition_path),
        shortage=joblib.load(shortage_path),
        policy=policy,
        model_dir=dest,
    )


def write_policy(model_dir: Path, policy: dict) -> None:
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "policy.json").write_text(json.dumps(policy, indent=2))
