"""History inspection and undo."""
from __future__ import annotations

from typing import Any

from .. import context
from . import tool


@tool(
    name="undo_last",
    description=(
        "Undo the most recent reversible action(s). "
        "Use this when the user says 'undo', 'undo that', or 'reverse the last thing'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "description": "Number of actions to undo (default 1).",
                "default": 1,
            }
        },
    },
)
async def undo_last(count: int = 1) -> dict[str, Any]:
    if context.session is None:
        return {"ok": False, "error": "session not initialized"}

    undone: list[str] = []
    skipped: list[str] = []

    while count > 0 and context.session.history:
        record = context.session.history.pop()
        if record.revert is None:
            skipped.append(record.tool_name)
            continue
        try:
            await record.revert()
            undone.append(record.tool_name)
            count -= 1
        except Exception as e:
            return {
                "ok": False,
                "error": f"undo failed for '{record.tool_name}': {e}",
                "undone": undone,
                "skipped": skipped,
            }

    if not undone:
        return {"ok": False, "error": "nothing to undo", "skipped": skipped}
    return {"ok": True, "undone": undone, "skipped": skipped}


@tool(
    name="recent_actions",
    description="List the last few actions taken, in reverse-chronological order.",
    input_schema={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "default": 5},
        },
    },
)
async def recent_actions(limit: int = 5) -> dict[str, Any]:
    if context.session is None:
        return {"ok": False, "error": "session not initialized"}
    items = list(context.session.history)[-limit:][::-1]
    return {
        "ok": True,
        "actions": [
            {
                "tool": r.tool_name,
                "input": r.tool_input,
                "ok": bool(r.result.get("ok", True)),
                "undoable": r.revert is not None,
            }
            for r in items
        ],
    }
