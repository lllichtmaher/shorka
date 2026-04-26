"""Speech-to-text. Provider-swappable: OpenAI (default) or Groq."""
from __future__ import annotations

import io
import wave
from typing import Optional

from openai import AsyncOpenAI

from .config import settings


_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if settings.stt_provider == "groq":
            _client = AsyncOpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        else:
            _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


def _model_id() -> str:
    if settings.stt_provider == "groq":
        return "whisper-large-v3-turbo"
    return settings.stt_model


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def transcribe(pcm: bytes) -> str:
    """Transcribe int16 mono PCM at settings.sample_rate_in. Returns the text (may be empty)."""
    if not pcm:
        return ""
    wav = _pcm_to_wav(pcm, settings.sample_rate_in)
    file_obj = io.BytesIO(wav)
    file_obj.name = "audio.wav"
    client = _get_client()
    resp = await client.audio.transcriptions.create(
        file=file_obj,
        model=_model_id(),
        response_format="text",
    )
    if isinstance(resp, str):
        return resp.strip()
    return getattr(resp, "text", "").strip()
