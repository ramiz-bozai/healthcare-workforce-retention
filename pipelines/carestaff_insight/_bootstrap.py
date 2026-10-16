"""Put the Git-folder repo root on sys.path so `src` and `data_generation` import.

Lakeflow source is often `pipelines/carestaff_insight`. This file lives there, so
parents[2] is the repository root whether you cloned to Repos or a Git folder.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
