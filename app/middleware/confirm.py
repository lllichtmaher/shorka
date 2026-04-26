"""Spoken yes/no confirmation gate for dangerous tools.

`request_confirmation` speaks a prompt, then awaits the user's next utterance via
a future on `session.pending_confirmation`. The main loop sees the future is set
and routes the next utterance into it instead of dispatching to Brain.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from .. import context


_YES = re.compile(
    r"\b(yes|yeah|yep|yup|sure|confirm|do it|go ahead|proceed|please do|okay|ok)\b",
    re.IGNORECASE,
)
_NO = re.compile(
    r"\b(no|nope|cancel|stop|don'?t|never\s?mind|abort|forget it|not now)\b",
    re.IGNORECASE,
)
_EXTEND = re.compile(
    r"\b(wait|hold on|let me think|one second|a moment|hang on|give me)\b",
    re.IGNORECASE,
)

CONFIRM_TIMEOUT_SEC = 10.0
MAX_REPROMPTS = 2


async def request_confirmation(action_description: str) -> str:
    """Returns 'confirmed' | 'denied' | 'timeout'."""
    if context.narrator is None or context.session is None:
        return "denied"

    loop = asyncio.get_running_loop()
    reprompts = 0

    await context.narrator.say(
        f"This will {action_description}. Say yes to confirm, or cancel."
    )

    while True:
        fut: asyncio.Future[str] = loop.create_future()
        context.session.pending_confirmation = fut
        try:
            try:
                utt = await asyncio.wait_for(fut, timeout=CONFIRM_TIMEOUT_SEC)
            except asyncio.TimeoutError:
                await context.narrator.say("No response. I'll cancel that.")
                return "timeout"
        finally:
            if context.session.pending_confirmation is fut:
                context.session.pending_confirmation = None

        text = utt.strip().lower()
        if _NO.search(text):
            return "denied"
        if _EXTEND.search(text) and not _YES.search(text):
            reprompts += 1
            if reprompts > MAX_REPROMPTS:
                await context.narrator.say("Cancelling.")
                return "denied"
            await context.narrator.say("Okay, take your time.")
            continue
        if _YES.search(text):
            return "confirmed"

        reprompts += 1
        if reprompts > MAX_REPROMPTS:
            await context.narrator.say("Cancelling.")
            return "denied"
        await context.narrator.say("I didn't catch that. Say yes to confirm, or cancel.")


async def gate(tool_name: str, tool_input: dict[str, Any], dangerous: bool) -> bool:
    """True ⇢ proceed; False ⇢ user denied or timed out."""
    if not dangerous:
        return True
    summary = _summarize(tool_name, tool_input)
    return await request_confirmation(summary) == "confirmed"


def _summarize(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Build a short spoken summary of the pending action."""
    pretty = tool_name.replace("_", " ")
    if not tool_input:
        return pretty
    args = ", ".join(f"{k}: {v}" for k, v in tool_input.items())
    return f"{pretty} — {args}"
