"""Keyboard input tools."""
from __future__ import annotations

from typing import Any

from ..os_layer import keyboard as os_kb
from . import tool


@tool(
    name="type_text",
    description=(
        "Type text into the currently focused field. "
        "Before calling, narrate what you're typing — and for personal info (emails, passwords, URLs) "
        "spell it out character by character in your narration so the user can verify."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to type. Goes to whatever window currently has keyboard focus.",
            }
        },
        "required": ["text"],
    },
)
async def type_text(text: str) -> dict[str, Any]:
    if not text:
        return {"ok": False, "error": "empty text"}
    try:
        os_kb.type_text(text)
        return {"ok": True, "typed_chars": len(text)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="press_keys",
    description=(
        "Press a single key or key combination. Use this for keyboard navigation — "
        "always prefer this over mouse clicks. "
        "Examples: 'enter', 'tab', 'escape', 'space', 'down', 'ctrl+s', 'ctrl+t', "
        "'alt+tab', 'ctrl+shift+t', 'win+r'."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "combo": {
                "type": "string",
                "description": "Key combination, '+' separated, e.g. 'ctrl+s' or 'enter'.",
            }
        },
        "required": ["combo"],
    },
)
async def press_keys(combo: str) -> dict[str, Any]:
    try:
        os_kb.press_keys(combo)
        return {"ok": True, "pressed": combo}
    except Exception as e:
        return {"ok": False, "error": str(e)}
