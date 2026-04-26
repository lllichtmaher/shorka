"""Screen-reading tools: UIA tree walking + OCR fallback."""
from __future__ import annotations

import asyncio
from typing import Any

from ..os_layer import ocr, uia
from . import tool


async def _to_thread(fn, *args, **kwargs):
    """Run a sync UIA call in the default executor; UIA tree walks can take 100ms+."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


@tool(
    name="describe_focus",
    description=(
        "Briefly describe the currently focused element and its containing window. "
        "Use this to orient the user after major actions."
    ),
    input_schema={"type": "object", "properties": {}},
)
async def describe_focus() -> dict[str, Any]:
    try:
        desc = await _to_thread(uia.describe_focus)
        return {"ok": True, "description": desc}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="list_focusable_elements",
    description=(
        "List keyboard-focusable elements in the currently focused window "
        "(buttons, links, fields, list items). "
        "ALWAYS call this BEFORE click_element — never invent element names."
    ),
    input_schema={"type": "object", "properties": {}},
)
async def list_focusable_elements() -> dict[str, Any]:
    try:
        elements = await _to_thread(uia.list_focusable)
        return {"ok": True, "elements": elements}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="click_element",
    description=(
        "Click an element by its exact name (and optionally role). "
        "The name MUST come from a recent list_focusable_elements call — do not invent names. "
        "Prefer keyboard navigation (press_keys) over clicking when possible."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Exact element name from list_focusable_elements."},
            "role": {
                "type": "string",
                "description": "Optional role filter, e.g. 'Button', 'Hyperlink', 'MenuItem'.",
            },
        },
        "required": ["name"],
    },
)
async def click_element(name: str, role: str = "") -> dict[str, Any]:
    try:
        ok = await _to_thread(uia.click_by_name, name, role or None)
        if ok:
            return {"ok": True, "clicked": name}
        return {"ok": False, "error": f"no focusable element named '{name}'"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="read_screen",
    description=(
        "Read the text content of the currently focused window. "
        "Returns up to 2500 chars from the UIA tree (falls back to OCR if empty). "
        "Use this when the user asks 'what's on screen' or 'what does it say'."
    ),
    input_schema={"type": "object", "properties": {}},
)
async def read_screen() -> dict[str, Any]:
    try:
        text = await _to_thread(uia.read_window_text)
        if not text.strip():
            text = await _to_thread(ocr.screenshot_ocr)
        return {"ok": True, "text": text or "(no readable text on screen)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="read_selection",
    description="Read the currently selected text in the focused field.",
    input_schema={"type": "object", "properties": {}},
)
async def read_selection() -> dict[str, Any]:
    try:
        text = await _to_thread(uia.read_selection)
        return {"ok": True, "text": text or "(nothing selected)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
