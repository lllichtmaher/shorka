"""Vision-based screen description using GPT-4o.

Takes a screenshot and sends it to a vision model to get a natural language
description. Works universally — browsers, games, native apps, anything visible.
"""
from __future__ import annotations

import asyncio
from typing import Any

from openai import AsyncOpenAI

from ..config import settings
from ..os_layer import screenshot
from . import tool


_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


@tool(
    name="see_screen",
    description=(
        "Take a screenshot of the ENTIRE screen and describe what's visible. "
        "Use this when the user asks 'what's on my screen', 'what do you see', "
        "'describe the screen', 'read the page', or any question about visual content. "
        "This works for EVERYTHING — browsers, apps, desktops, videos. "
        "Much more reliable than read_screen for browser content."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": (
                    "Optional specific question about the screen, e.g. "
                    "'what website is open?' or 'what are the search results?'. "
                    "If not provided, gives a general description."
                ),
            },
        },
    },
)
async def see_screen(question: str = "") -> dict[str, Any]:
    img_b64 = await asyncio.get_running_loop().run_in_executor(
        None, screenshot.capture_screenshot
    )
    if img_b64 is None:
        return {"ok": False, "error": "Failed to capture screenshot. PIL may not be installed."}

    prompt = (
        "You are a screen reader for a blind user. Describe what you see on this screen "
        "in clear, concise spoken language. Focus on:\n"
        "1. What application or website is in the foreground\n"
        "2. The main content visible (text, images, UI elements)\n"
        "3. Any actionable items (buttons, links, input fields)\n"
        "4. The current state (loading, error, form filled, etc.)\n\n"
        "Keep it brief — 2-4 sentences max. Speak as if narrating to a blind person.\n"
        "Do NOT use markdown, lists, or formatting. Just natural spoken prose."
    )
    if question:
        prompt += f"\n\nThe user specifically asked: {question}"

    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
        )
        description = response.choices[0].message.content or "(no description)"
        return {"ok": True, "description": description}
    except Exception as e:
        return {"ok": False, "error": f"Vision API error: {e}"}


@tool(
    name="find_on_screen",
    description=(
        "Take a screenshot and find a specific element, button, or text on screen. "
        "Use this to locate something visually before clicking or interacting with it. "
        "Returns the approximate location and description of the element."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": "What to look for, e.g. 'the search bar', 'the play button', 'the login link'.",
            },
        },
        "required": ["target"],
    },
)
async def find_on_screen(target: str) -> dict[str, Any]:
    img_b64 = await asyncio.get_running_loop().run_in_executor(
        None, screenshot.capture_screenshot
    )
    if img_b64 is None:
        return {"ok": False, "error": "Failed to capture screenshot."}

    prompt = (
        f"You are helping a blind user find '{target}' on their screen. "
        f"Look at this screenshot and tell me:\n"
        f"1. Is '{target}' visible on screen? (yes/no)\n"
        f"2. If yes, describe exactly where it is (e.g. 'top-right corner', 'center of page', "
        f"'in the navigation bar at the top')\n"
        f"3. What's the best way to reach it via keyboard? (e.g. 'Tab 3 times', 'use Ctrl+L for address bar')\n\n"
        f"Answer in natural spoken prose, brief — 1-2 sentences. No markdown."
    )

    client = _get_client()
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{img_b64}",
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
        )
        result = response.choices[0].message.content or "(could not analyze)"
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": f"Vision API error: {e}"}
