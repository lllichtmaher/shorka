"""Single owner of the system audio device.

Why a single owner: opening separate sounddevice InputStream and OutputStream from
different components races on PortAudio's device handles. Centralizing here also
lets us mix TTS + cues with proper ducking in one callback.
"""
from __future__ import annotations

import asyncio
import threading
from typing import AsyncIterator, Optional

import numpy as np
import sounddevice as sd

from .config import settings


_INT16_MAX = 32767


class AudioBus:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._in_q: Optional[asyncio.Queue[bytes]] = None
        self._tts_buf = bytearray()
        self._cue_buf = bytearray()
        self._buf_lock = threading.Lock()
        self._in_stream: Optional[sd.InputStream] = None
        self._out_stream: Optional[sd.OutputStream] = None

        # Frames per callback. Match silero-vad's required 512 samples at 16 kHz.
        self._in_block = 512
        self._out_block = 480  # 20 ms at 24 kHz

    @property
    def is_playing(self) -> bool:
        with self._buf_lock:
            return len(self._tts_buf) > 0

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._in_q = asyncio.Queue(maxsize=128)

        def in_callback(indata, frames, time_info, status):  # noqa: ANN001
            if status:
                # Drop on overflow — better to lose a chunk than block the audio thread.
                pass
            pcm = (indata[:, 0] * _INT16_MAX).clip(-_INT16_MAX, _INT16_MAX).astype(np.int16).tobytes()

            def _enqueue(data: bytes = pcm) -> None:
                try:
                    self._in_q.put_nowait(data)
                except asyncio.QueueFull:
                    pass  # Drop chunk rather than crash

            try:
                self._loop.call_soon_threadsafe(_enqueue)
            except RuntimeError:
                pass

        def out_callback(outdata, frames, time_info, status):  # noqa: ANN001
            bytes_needed = frames * 2  # int16 mono
            with self._buf_lock:
                tts_chunk = self._take(self._tts_buf, bytes_needed)
                cue_chunk = self._take(self._cue_buf, bytes_needed)

            tts = np.frombuffer(tts_chunk, dtype=np.int16).astype(np.float32) / _INT16_MAX
            cue = np.frombuffer(cue_chunk, dtype=np.int16).astype(np.float32) / _INT16_MAX
            cue_active = bool(np.any(cue))
            mixed = tts * 0.5 + cue if cue_active else tts
            np.clip(mixed, -1.0, 1.0, out=mixed)
            outdata[:, 0] = mixed

        self._in_stream = sd.InputStream(
            samplerate=settings.sample_rate_in,
            channels=1,
            dtype="float32",
            blocksize=self._in_block,
            callback=in_callback,
        )
        self._out_stream = sd.OutputStream(
            samplerate=settings.sample_rate_out,
            channels=1,
            dtype="float32",
            blocksize=self._out_block,
            callback=out_callback,
        )
        self._in_stream.start()
        self._out_stream.start()

    def stop(self) -> None:
        for s in (self._in_stream, self._out_stream):
            if s is not None:
                try:
                    s.stop()
                    s.close()
                except Exception:
                    pass
        self._in_stream = None
        self._out_stream = None

    async def record_chunks(self) -> AsyncIterator[bytes]:
        assert self._in_q is not None, "AudioBus.start() must be called first"
        while True:
            yield await self._in_q.get()

    def play_tts(self, pcm: bytes) -> None:
        with self._buf_lock:
            self._tts_buf.extend(pcm)

    def play_cue(self, pcm: bytes) -> None:
        with self._buf_lock:
            self._cue_buf.extend(pcm)

    def flush_tts(self) -> None:
        with self._buf_lock:
            self._tts_buf.clear()

    async def wait_tts_drained(self) -> None:
        while self.is_playing:
            await asyncio.sleep(0.02)

    @staticmethod
    def _take(buf: bytearray, n: int) -> bytes:
        if len(buf) >= n:
            chunk = bytes(buf[:n])
            del buf[:n]
            return chunk
        chunk = bytes(buf) + b"\x00" * (n - len(buf))
        buf.clear()
        return chunk
