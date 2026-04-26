"""Web tools: open URLs and search the web in the default browser."""
from __future__ import annotations

import os
import urllib.parse
from typing import Any

from . import tool


def _open(url: str) -> None:
    os.startfile(url)  # Windows-only; opens with default app association.


@tool(
    name="open_url",
    description="Open a URL in the default web browser.",
    input_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to open. May omit 'https://'."}
        },
        "required": ["url"],
    },
)
async def open_url(url: str) -> dict[str, Any]:
    if not url.startswith(("http://", "https://", "file://")):
        url = "https://" + url
    try:
        _open(url)
        return {"ok": True, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@tool(
    name="web_search",
    description=(
        "Open a Google search for the given query in the default browser. "
        "Use this when the user asks to search for or look up something on the web."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."}
        },
        "required": ["query"],
    },
)
async def web_search(query: str) -> dict[str, Any]:
    url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
    try:
        _open(url)
        return {"ok": True, "query": query, "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e)}
