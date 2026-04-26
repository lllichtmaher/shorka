"""App launch and window-management tools."""
from __future__ import annotations

from typing import Any

from .. import context
from ..os_layer import apps_index, windows as os_windows
from . import tool


@tool(
    name="launch_app",
    description=(
        "Launch a Windows application by name. Uses fuzzy matching against installed apps. "
        "Use this when the user asks to open, start, or launch any program (Chrome, Spotify, Notepad, etc)."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The app name to launch, e.g. 'Chrome', 'Spotify', 'Microsoft Word'.",
            }
        },
        "required": ["name"],
    },
)
async def launch_app(name: str) -> dict[str, Any]:
    matches = apps_index.find(name, limit=5)
    if not matches:
        return {"ok": False, "error": f"No installed app matches '{name}'."}
    target = matches[0]
    alternatives = [m.get("Name", "") for m in matches[1:4]]
    aumid = target.get("AppID")
    if not aumid:
        return {"ok": False, "error": f"App '{target.get('Name')}' has no launch ID."}
    try:
        apps_index.launch(aumid)
        # Register undo: best-effort close-by-title.
        launched_name = target.get("Name", aumid)
        if context.session is not None:
            async def _revert() -> None:
                os_windows.close_window(launched_name)
            context.session.last_revert = _revert
        return {
            "ok": True,
            "launched": launched_name,
            "alternatives": alternatives,
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "alternatives": alternatives}


@tool(
    name="list_windows",
    description="List all currently visible top-level windows on the desktop.",
    input_schema={"type": "object", "properties": {}},
)
async def list_windows() -> dict[str, Any]:
    try:
        wins = os_windows.list_windows()
        return {"ok": True, "windows": [w["title"] for w in wins]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="focus_window",
    description=(
        "Bring an open window to the foreground by partial title match. "
        "Use this to switch between already-open apps."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Part of the window title to match, e.g. 'Chrome' or 'gmail'.",
            }
        },
        "required": ["title"],
    },
)
async def focus_window(title: str) -> dict[str, Any]:
    try:
        return os_windows.focus_window(title)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="close_window",
    description=(
        "Close an open window by partial title match. "
        "Dangerous — the user will be asked to confirm. "
        "If the app has unsaved changes, the app may show its own save-prompt dialog."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Part of the window title to match.",
            }
        },
        "required": ["title"],
    },
    dangerous=True,
)
async def close_window(title: str) -> dict[str, Any]:
    try:
        return os_windows.close_window(title)
    except Exception as e:
        return {"ok": False, "error": str(e)}
