"""Mic → silero-vad → utterance buffer → STT, with wake word session gating.

States:
  IDLE     — ignoring everything except the wake word "Shorka"
  ACTIVE   — every utterance is sent as a command; stays active until dismissed
             or after inactivity timeout
"""
from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import AsyncIterator, Awaitable, Callable, Optional

import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad

from . import cues, wake_word
from .audio_bus import AudioBus
from .config import settings
from .stt import transcribe

# After this many seconds of silence in ACTIVE mode, go back to IDLE.
INACTIVITY_TIMEOUT_S = 60.0


class _State(Enum):
    IDLE = auto()
    ACTIVE = auto()


@dataclass
class Utterance:
    text: str
    audio_pcm: bytes


class DismissEvent:
    """Sentinel yielded when the user dismisses Shorka."""
    pass


class Listener:
    def __init__(
        self,
        bus: AudioBus,
        on_speech_start: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        self.bus = bus
        self.on_speech_start = on_speech_start

        model = load_silero_vad()
        self._vad = VADIterator(
            model,
            threshold=settings.vad_threshold,
            sampling_rate=settings.sample_rate_in,
            min_silence_duration_ms=settings.vad_min_silence_ms,
        )
        self._buffer = bytearray()
        self._capturing = False
        self._state = _State.IDLE
        self._last_activity = time.monotonic()

    @property
    def is_active(self) -> bool:
        return self._state == _State.ACTIVE

    def _activate(self) -> None:
        self._state = _State.ACTIVE
        self._last_activity = time.monotonic()
        print("[listener] → ACTIVE", file=sys.stderr)

    def _deactivate(self) -> None:
        self._state = _State.IDLE
        print("[listener] → IDLE", file=sys.stderr)

    async def utterances(self) -> AsyncIterator[Utterance | DismissEvent]:
        min_bytes = int(settings.sample_rate_in * settings.min_utterance_ms / 1000) * 2

        async for chunk in self.bus.record_chunks():
            # Check inactivity timeout while active
            if self._state == _State.ACTIVE:
                if time.monotonic() - self._last_activity > INACTIVITY_TIMEOUT_S:
                    cues.play(self.bus, "listening_end")
                    self._deactivate()
                    yield DismissEvent()
                    continue

            samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32767.0
            tensor = torch.from_numpy(samples)
            event = self._vad(tensor, return_seconds=False)

            if event is not None and "start" in event:
                self._capturing = True
                self._buffer.clear()
                if self._state == _State.ACTIVE:
                    cues.play(self.bus, "listening_start")
                    if self.on_speech_start is not None:
                        asyncio.create_task(self.on_speech_start())

            if self._capturing:
                self._buffer.extend(chunk)

            if event is not None and "end" in event:
                self._capturing = False
                pcm = bytes(self._buffer)
                self._buffer.clear()
                if len(pcm) < min_bytes:
                    continue

                # Transcribe the speech
                try:
                    text = await transcribe(pcm)
                except Exception as e:
                    cues.play(self.bus, "error")
                    print(f"[stt] error: {e}", file=sys.stderr)
                    continue
                if not text:
                    continue

                if self._state == _State.IDLE:
                    # --- IDLE: only react to wake word ---
                    detected, remaining = wake_word.detect(text)
                    if detected:
                        print(f"[wake] detected in: {text!r}", file=sys.stderr)
                        cues.play(self.bus, "wake")
                        self._activate()
                        if remaining.strip():
                            # Wake word + command in same breath
                            # e.g. "Hey Shorka, open Spotify"
                            cues.play(self.bus, "listening_end")
                            yield Utterance(text=remaining.strip(), audio_pcm=pcm)
                        # else: just the wake word — stay active, wait for next utterance

                elif self._state == _State.ACTIVE:
                    self._last_activity = time.monotonic()

                    # Check for dismiss command
                    if wake_word.is_dismiss(text):
                        print(f"[listener] dismiss: {text!r}", file=sys.stderr)
                        cues.play(self.bus, "listening_end")
                        self._deactivate()
                        yield DismissEvent()
                        continue

                    # Also check if they said the wake word again — just refresh, don't
                    # treat it as a command
                    detected, remaining = wake_word.detect(text)
                    if detected:
                        if remaining.strip():
                            cues.play(self.bus, "listening_end")
                            yield Utterance(text=remaining.strip(), audio_pcm=pcm)
                        # else: they just said "shorka" again — stay active
                        continue

                    # Normal command
                    cues.play(self.bus, "listening_end")
                    yield Utterance(text=text, audio_pcm=pcm)
