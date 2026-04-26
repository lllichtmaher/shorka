"""Lightweight HTTP control API for the Flutter frontend.

Runs an asyncio-based HTTP server on localhost:8412 that the Flutter overlay
can call to control Shorka (toggle mic, switch voice, check status, etc.).
"""
from __future__ import annotations

import asyncio
import json
import sys
from http import HTTPStatus
from typing import Any, Callable, Awaitable, Optional

from . import context


_PORT = 8412
_server: Optional[asyncio.Server] = None

# Callbacks set by main.py
_on_toggle_listen: Optional[Callable[[], Awaitable[None]]] = None
_on_force_dismiss: Optional[Callable[[], Awaitable[None]]] = None


def set_callbacks(
    on_toggle_listen: Callable[[], Awaitable[None]],
    on_force_dismiss: Callable[[], Awaitable[None]],
) -> None:
    global _on_toggle_listen, _on_force_dismiss
    _on_toggle_listen = on_toggle_listen
    _on_force_dismiss = on_force_dismiss


async def start() -> None:
    global _server
    _server = await asyncio.start_server(_handle_connection, "127.0.0.1", _PORT)
    print(f"[api] listening on http://127.0.0.1:{_PORT}", file=sys.stderr)


async def stop() -> None:
    global _server
    if _server is not None:
        _server.close()
        await _server.wait_closed()
        _server = None


async def _handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        request, body = await asyncio.wait_for(_read_request(reader), timeout=5.0)
        method, path = _parse_request_line(request)

        # CORS headers for Flutter web (also works for desktop HTTP calls)
        cors = (
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
        )

        if method == "OPTIONS":
            _send_response(writer, 200, "{}", extra_headers=cors)
        elif path == "/status":
            _send_response(writer, 200, json.dumps(_get_status()), extra_headers=cors)
        elif path == "/toggle-listen":
            result = await _handle_toggle_listen()
            _send_response(writer, 200, json.dumps(result), extra_headers=cors)
        elif path == "/set-voice" and method == "POST":
            result = await _handle_set_voice(body)
            _send_response(writer, 200, json.dumps(result), extra_headers=cors)
        elif path == "/voices":
            result = _get_voices()
            _send_response(writer, 200, json.dumps(result), extra_headers=cors)
        elif path == "/transcript":
            result = _get_transcript()
            _send_response(writer, 200, json.dumps(result), extra_headers=cors)
        elif path == "/dismiss":
            result = await _handle_dismiss()
            _send_response(writer, 200, json.dumps(result), extra_headers=cors)
        else:
            _send_response(writer, 404, json.dumps({"error": "not found"}), extra_headers=cors)

        await writer.drain()
    except Exception as e:
        print(f"[api] error: {e}", file=sys.stderr)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, dict]:
    """Read full HTTP request: headers + body (Content-Length or chunked)."""
    header_bytes = await reader.readuntil(b"\r\n\r\n")
    header_str = header_bytes.decode("utf-8", errors="replace")
    content_length = 0
    chunked = False
    for line in header_str.split("\r\n"):
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        kl = k.strip().lower()
        if kl == "content-length":
            try:
                content_length = int(v.strip())
            except ValueError:
                content_length = 0
        elif kl == "transfer-encoding" and "chunked" in v.lower():
            chunked = True

    body_bytes = b""
    if chunked:
        # Read chunks: "<hex_size>\r\n<data>\r\n", terminated by "0\r\n\r\n"
        while True:
            size_line = await reader.readuntil(b"\r\n")
            size_str = size_line.strip().split(b";")[0]
            try:
                size = int(size_str, 16)
            except ValueError:
                break
            if size == 0:
                await reader.readuntil(b"\r\n")  # trailing CRLF after the zero-chunk
                break
            body_bytes += await reader.readexactly(size)
            await reader.readexactly(2)  # CRLF after chunk data
    elif content_length > 0:
        body_bytes = await reader.readexactly(content_length)

    body: dict = {}
    if body_bytes:
        try:
            body = json.loads(body_bytes.decode("utf-8", errors="replace"))
            if not isinstance(body, dict):
                body = {}
        except (json.JSONDecodeError, ValueError):
            body = {}
    return header_str, body


def _parse_request_line(request: str) -> tuple[str, str]:
    first_line = request.split("\r\n", 1)[0]
    parts = first_line.split(" ")
    if len(parts) >= 2:
        return parts[0].upper(), parts[1]
    return "GET", "/"


def _send_response(writer: asyncio.StreamWriter, status: int, body: str, extra_headers: str = "") -> None:
    reason = HTTPStatus(status).phrase
    response = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body.encode())}\r\n"
        f"{extra_headers}"
        f"Connection: close\r\n"
        f"\r\n"
        f"{body}"
    )
    writer.write(response.encode())


def _get_status() -> dict[str, Any]:
    """Return current app state for the frontend."""
    listener = getattr(context, '_listener', None)

    is_active = False
    if listener is not None:
        is_active = listener.is_active

    current_voice = ""
    last_user = ""
    last_assistant = ""
    pending = False
    if context.session:
        current_voice = context.session.current_voice_key
        pending = context.session.pending_confirmation is not None
        for line in reversed(context.session.transcript):
            if not last_assistant and line.role == "assistant":
                last_assistant = line.text
            if not last_user and line.role == "user":
                last_user = line.text
            if last_assistant and last_user:
                break

    return {
        "ok": True,
        "listening": is_active,
        "voice": current_voice,
        "speaking": context.narrator.is_speaking if context.narrator else False,
        "awaiting_confirm": pending,
        "last_user": last_user,
        "last_assistant": last_assistant,
    }


def _get_transcript() -> dict[str, Any]:
    if context.session is None:
        return {"ok": False, "error": "not initialized"}
    return {
        "ok": True,
        "lines": [
            {"role": line.role, "text": line.text, "ts": line.timestamp}
            for line in context.session.transcript
        ],
    }


def _get_voices() -> dict[str, Any]:
    if context.voices is None:
        return {"ok": False, "error": "not initialized"}
    return {
        "ok": True,
        "voices": [
            {"key": v.key, "name": v.name, "aliases": v.aliases}
            for v in context.voices.all()
        ],
        "current": context.session.current_voice_key if context.session else "",
    }


async def _handle_toggle_listen() -> dict[str, Any]:
    if _on_toggle_listen is not None:
        await _on_toggle_listen()
        return {"ok": True, "action": "toggled"}
    return {"ok": False, "error": "not ready"}


async def _handle_set_voice(body: dict) -> dict[str, Any]:
    name = body.get("name", "")
    if not name:
        return {"ok": False, "error": "missing 'name'"}
    if context.voices is None or context.narrator is None or context.session is None:
        return {"ok": False, "error": "not initialized"}

    profile = context.voices.find(name)
    if profile is None:
        available = [v.name for v in context.voices.all()]
        return {"ok": False, "error": f"No voice matches '{name}'", "available": available}

    if profile.id != context.session.current_voice_id:
        await context.narrator.interrupt()
        context.narrator.set_voice(profile.id)
        context.session.current_voice_id = profile.id
        context.session.current_voice_key = profile.key
        await context.narrator.say(f"Switched to {profile.name}.")

    return {"ok": True, "voice": profile.name}


async def _handle_dismiss() -> dict[str, Any]:
    if _on_force_dismiss is not None:
        await _on_force_dismiss()
        return {"ok": True, "action": "dismissed"}
    return {"ok": False, "error": "not ready"}
