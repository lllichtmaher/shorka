"""Explicit confirmation tool. Dangerous tools are gated automatically by middleware;
use this only when the user explicitly asks for a confirmation step."""
from __future__ import annotations

from typing import Any

from ..middleware import confirm as confirm_mw
from . import tool


@tool(
    name="request_confirmation",
    description=(
        "Explicitly request a yes/no confirmation from the user. "
        "Returns 'confirmed', 'denied', or 'timeout'. "
        "You usually do NOT need this — the system gates dangerous tools automatically."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "action_description": {
                "type": "string",
                "description": "Short description of what will happen, e.g. 'delete report.docx'.",
            }
        },
        "required": ["action_description"],
    },
)
async def request_confirmation(action_description: str) -> dict[str, Any]:
    result = await confirm_mw.request_confirmation(action_description)
    return {"ok": True, "result": result}
