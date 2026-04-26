"""Voice profile switching tools."""
from __future__ import annotations

from typing import Any

from .. import context
from . import tool


@tool(
    name="list_voices",
    description=(
        "List the available TTS voice profiles. Use when the user asks 'what voices are there' "
        "or before switching if you don't know what's available."
    ),
    input_schema={"type": "object", "properties": {}},
)
async def list_voices() -> dict[str, Any]:
    if context.voices is None:
        return {"ok": False, "error": "voices not initialized"}
    return {
        "ok": True,
        "voices": [
            {"key": v.key, "name": v.name, "aliases": v.aliases}
            for v in context.voices.all()
        ],
        "current": context.session.current_voice_key if context.session else "",
    }


@tool(
    name="set_voice",
    description=(
        "Switch the TTS voice. Accepts a friendly name, key, or alias "
        "(e.g. 'Rachel', 'British', 'soft'). Confirms in the new voice."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Voice name, key, or alias to switch to.",
            }
        },
        "required": ["name"],
    },
)
async def set_voice(name: str) -> dict[str, Any]:
    if context.voices is None or context.narrator is None or context.session is None:
        return {"ok": False, "error": "voice subsystem not initialized"}
    profile = context.voices.find(name)
    if profile is None:
        available = [v.name for v in context.voices.all()]
        return {
            "ok": False,
            "error": f"No voice matches '{name}'.",
            "available": available,
        }
    if profile.id == context.session.current_voice_id:
        return {"ok": True, "voice": profile.name, "note": "already using this voice"}

    await context.narrator.interrupt()
    context.narrator.set_voice(profile.id)
    context.session.current_voice_id = profile.id
    context.session.current_voice_key = profile.key
    await context.narrator.say(f"Switched to {profile.name}.")
    return {"ok": True, "voice": profile.name}
