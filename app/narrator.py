"""ElevenLabs WebSocket streaming TTS with mid-utterance interrupt."""
from __future__ import annotations

import asyncio
import base64
import json
from typing import AsyncIterator, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from .audio_bus import AudioBus
from .config import settings


def _ws_url(voice_id: str) -> str:
    return (
        f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream-input"
        f"?model_id={settings.elevenlabs_model}"
        f"&output_format={settings.elevenlabs_output_format}"
    )


class Narrator:
    def __init__(self, bus: AudioBus, voice_id: str) -> None:
        self.bus = bus
        self.voice_id = voice_id
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._speak_task: Optional[asyncio.Task] = None
        self._streaming = False

    @property
    def is_speaking(self) -> bool:
        return self._streaming or self.bus.is_playing

    def set_voice(self, voice_id: str) -> None:
        """Take effect on next utterance. Use interrupt() first if mid-speech."""
        self.voice_id = voice_id

    async def say(self, text: str) -> None:
        """Block until audio for `text` has been fully played (or interrupted)."""
        await self._speak_chunks(_single(text))

    async def say_streaming(self, chunks: AsyncIterator[str]) -> None:
        """Stream text chunks (e.g. from Claude) into TTS as they arrive."""
        await self._speak_chunks(chunks)

    def speak_async(self, text: str) -> asyncio.Task:
        """Start saying `text` without awaiting. Returns task; call interrupt() to stop."""
        if self._speak_task is not None and not self._speak_task.done():
            self._speak_task.cancel()
        self._speak_task = asyncio.create_task(self.say(text))
        return self._speak_task

    async def interrupt(self) -> None:
        """Halt current TTS immediately and flush queued audio.

        Order matters: flush audio buffer FIRST so the user perceives stop within
        ~20 ms (one output callback period), then tear down the WebSocket and
        cancel the speak task. Re-flush at the end in case the receiver enqueued
        more audio between the first flush and the WS close.
        """
        self.bus.flush_tts()
        self._streaming = False
        ws, self._ws = self._ws, None
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                pass
        if self._speak_task is not None and not self._speak_task.done():
            self._speak_task.cancel()
            try:
                await self._speak_task
            except (asyncio.CancelledError, Exception):
                pass
            self._speak_task = None
        self.bus.flush_tts()

    async def _speak_chunks(self, chunks: AsyncIterator[str]) -> None:
        url = _ws_url(self.voice_id)
        headers = {"xi-api-key": settings.elevenlabs_api_key}
        self._streaming = True
        try:
            async with websockets.connect(url, additional_headers=headers) as ws:
                self._ws = ws
                # BOS: voice settings + leading space (required by API).
                await ws.send(json.dumps({
                    "text": " ",
                    "voice_settings": {
                        "stability": settings.elevenlabs_stability,
                        "similarity_boost": settings.elevenlabs_similarity_boost,
                    },
                }))

                async def sender():
                    try:
                        async for chunk in chunks:
                            if not chunk:
                                continue
                            await ws.send(json.dumps({"text": chunk, "try_trigger_generation": True}))
                        await ws.send(json.dumps({"text": ""}))  # EOS
                    except ConnectionClosed:
                        pass

                async def receiver():
                    try:
                        async for raw in ws:
                            data = json.loads(raw)
                            audio_b64 = data.get("audio")
                            if audio_b64:
                                self.bus.play_tts(base64.b64decode(audio_b64))
                            if data.get("isFinal"):
                                break
                    except ConnectionClosed:
                        pass

                await asyncio.gather(sender(), receiver())
            await self.bus.wait_tts_drained()
        except asyncio.CancelledError:
            self.bus.flush_tts()
            raise
        finally:
            self._ws = None
            self._streaming = False


async def _single(text: str) -> AsyncIterator[str]:
    yield text
