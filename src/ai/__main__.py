"""Ask the local allowlisted assistant.

    uv run python -m src.ai "What is 7-day coverage?"
    uv run python -m src.ai --list-tools
"""

from __future__ import annotations

import argparse
import sys

from src.ai.assistant import ask
from src.ai.tools import TOOLS, TOOL_TABLES
from src.common.paths import DEFAULT_DUCKDB, MODEL_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="CareStaff Insight allowlisted assistant (template mode).")
    parser.add_argument("question", nargs="?", default=None)
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--duckdb", default=DEFAULT_DUCKDB)
    parser.add_argument("--model-dir", default=MODEL_DIR)
    parser.add_argument("--profile", choices=("seed", "demo"), default="seed")
    args = parser.parse_args()
    if args.list_tools:
        for tool_id in TOOLS:
            tables = ", ".join(TOOL_TABLES[tool_id])
            print(f"{tool_id:24} {tables}")
        print("Genie is not live. Model Serving is not live. Template mode.")
        return
    if not args.question:
        parser.error("question required (or pass --list-tools)")
    turn = ask(
        args.question,
        duckdb_path=args.duckdb,
        model_dir=args.model_dir,
        profile=args.profile,
    )
    print(turn.answer)
    print()
    print(
        f"intent={turn.intent} tools={','.join(turn.tools_called) or '-'} "
        f"valid={turn.valid} mode={turn.mode} genie_live={turn.genie_live} "
        f"model_serving_live={turn.model_serving_live}"
    )
    if turn.unmatched:
        print("unmatched:", ", ".join(turn.unmatched), file=sys.stderr)
        sys.exit(2)
    if not turn.valid:
        sys.exit(2)


if __name__ == "__main__":
    main()
