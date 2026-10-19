"""Turn gold frames into JSON. No derived KPIs."""

from __future__ import annotations

import json

import pandas as pd


def records(frame: pd.DataFrame) -> list[dict]:
    if frame is None or frame.empty:
        return []
    payload = frame.to_json(orient="records", date_format="iso")
    return json.loads(payload)


def row(frame: pd.DataFrame) -> dict:
    rows = records(frame)
    if not rows:
        raise FileNotFoundError("Expected one gold row, got none.")
    return rows[0]
