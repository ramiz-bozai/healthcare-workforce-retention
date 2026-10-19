"""Call a workspace Genie space from the App. Live only when a space ID is set."""

from __future__ import annotations

import os
from datetime import timedelta

GENIE_ENV_KEYS = ("GENIE_SPACE_ID", "DATABRICKS_GENIE_SPACE_ID", "CARESTAFF_GENIE_SPACE_ID")


def space_id() -> str | None:
    for key in GENIE_ENV_KEYS:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def is_live() -> bool:
    return space_id() is not None


def _text(attachment) -> str:
    text = getattr(attachment, "text", None)
    return str(getattr(text, "content", "") or "").strip() if text is not None else ""


def _sql(attachment) -> dict | None:
    query = getattr(attachment, "query", None)
    if query is None:
        return None
    sql = getattr(query, "query", None)
    if not sql:
        return None
    return {
        "title": getattr(query, "title", None),
        "description": getattr(query, "description", None),
        "sql": sql,
        "attachment_id": getattr(query, "id", None) or getattr(attachment, "attachment_id", None),
    }


def _suggested(attachment) -> list[str]:
    block = getattr(attachment, "suggested_questions", None)
    if block is None:
        return []
    questions = getattr(block, "questions", None) or getattr(block, "suggested_questions", None) or []
    out = []
    for item in questions:
        if isinstance(item, str):
            out.append(item)
        else:
            q = getattr(item, "question", None) or getattr(item, "content", None)
            if q:
                out.append(str(q))
    return out


def _rows_from_statement(statement) -> list[dict]:
    if statement is None:
        return []
    manifest = getattr(statement, "manifest", None)
    result = getattr(statement, "result", None)
    schema = getattr(manifest, "schema", None) if manifest is not None else None
    columns = []
    if schema is not None:
        for col in getattr(schema, "columns", None) or []:
            columns.append(getattr(col, "name", None) or f"c{len(columns)}")
    data = getattr(result, "data_array", None) if result is not None else None
    if not data:
        return []
    rows = []
    for raw in data[:24]:
        values = list(raw)
        if columns:
            rows.append({columns[i]: values[i] if i < len(values) else None for i in range(len(columns))})
        else:
            rows.append({f"c{i}": v for i, v in enumerate(values)})
    return rows


def _query_rows(client, space: str, conversation_id: str, message_id: str, attachment_id: str | None) -> list[dict]:
    try:
        if attachment_id:
            payload = client.genie.get_message_attachment_query_result(
                space_id=space,
                conversation_id=conversation_id,
                message_id=message_id,
                attachment_id=attachment_id,
            )
        else:
            payload = client.genie.get_message_query_result(
                space_id=space,
                conversation_id=conversation_id,
                message_id=message_id,
            )
    except Exception:
        return []
    statement = getattr(payload, "statement_response", None)
    return _rows_from_statement(statement)


def message_to_payload(client, space: str, message, question: str) -> dict:
    attachments = list(getattr(message, "attachments", None) or [])
    texts: list[str] = []
    sql_blocks: list[dict] = []
    suggested: list[str] = []
    rows: list[dict] = []
    conversation_id = getattr(message, "conversation_id", None)
    message_id = getattr(message, "id", None) or getattr(message, "message_id", None)
    for attachment in attachments:
        chunk = _text(attachment)
        if chunk:
            texts.append(chunk)
        block = _sql(attachment)
        if block:
            sql_blocks.append(block)
            fetched = _query_rows(client, space, conversation_id, message_id, block.get("attachment_id"))
            if fetched and not rows:
                rows = fetched
        suggested.extend(_suggested(attachment))
    error = getattr(message, "error", None)
    err_text = str(getattr(error, "error", None) or error or "") if error else ""
    answer = "\n\n".join(texts).strip() or err_text or "Genie returned no narrative. SQL is below if it ran."
    return {
        "question": question,
        "answer": answer,
        "intent": "genie",
        "tools_called": ["genie"],
        "valid": True,
        "unmatched": [],
        "mode": "genie",
        "genie_live": True,
        "model_serving_live": False,
        "conversation_id": conversation_id,
        "sql": sql_blocks,
        "rows": rows,
        "suggested": suggested,
        "error": err_text or None,
    }


def ask_genie(question: str, conversation_id: str | None = None) -> dict:
    space = space_id()
    if not space:
        raise RuntimeError("Genie space is not attached. Add a Genie Agent resource to the App.")
    from databricks.sdk import WorkspaceClient

    client = WorkspaceClient()
    timeout = timedelta(seconds=90)
    if conversation_id:
        message = client.genie.create_message_and_wait(
            space_id=space,
            conversation_id=conversation_id,
            content=question,
            timeout=timeout,
        )
    else:
        message = client.genie.start_conversation_and_wait(
            space_id=space,
            content=question,
            timeout=timeout,
        )
    return message_to_payload(client, space, message, question)
