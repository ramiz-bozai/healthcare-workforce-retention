"""CareStaff Insight workbench — FastAPI + React.

    uv run uvicorn app:app --reload --port 8000
    cd frontend && npm run dev

Does not apply actions. Not Model Serving.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.app.api import (
    SAMPLE_QUESTIONS,
    actions_payload,
    ask_payload,
    attrition_detail_payload,
    attrition_payload,
    overview_payload,
    policy_payload,
    shortage_payload,
)
from src.app.connection import open_gold
from src.app.format import DISCLAIMER
from src.app.genie import is_live
from src.app.load import model_dir, require_gold

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="CareStaff Insight", docs_url=None, redoc_url=None, openapi_url=None)


class AskBody(BaseModel):
    question: str
    conversation_id: str | None = None


@contextmanager
def gold():
    con = open_gold()
    try:
        require_gold(con)
        yield con
    finally:
        con.close()


def _run(fn, *args, **kwargs):
    try:
        with gold() as con:
            return fn(con, *args, **kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "disclaimer": DISCLAIMER,
        "sample_questions": SAMPLE_QUESTIONS,
        "model_dir": str(model_dir()),
        "apply_enabled": False,
        "serving": "in_process_predict",
        "genie_live": is_live(),
    }


@app.get("/api/overview")
def overview():
    return _run(overview_payload)


@app.get("/api/attrition")
def attrition():
    return _run(attrition_payload)


@app.get("/api/attrition/{employee_id}")
def attrition_detail(employee_id: str):
    return _run(attrition_detail_payload, employee_id)


@app.get("/api/shortage")
def shortage():
    return _run(shortage_payload)


@app.get("/api/actions")
def actions(playbook: str = "(all)"):
    return _run(actions_payload, playbook)


@app.get("/api/policy")
def policy():
    return _run(policy_payload)


@app.post("/api/ask")
def ask_route(body: AskBody):
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question required")
    return _run(ask_payload, question, body.conversation_id)


if FRONTEND_DIST.is_dir():
    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        index = FRONTEND_DIST / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="frontend not built")
        return FileResponse(index)


def main() -> None:
    import uvicorn

    port = int(os.environ.get("DATABRICKS_APP_PORT") or os.environ.get("PORT") or 8000)
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()
