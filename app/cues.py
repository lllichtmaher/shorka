"""Short non-verbal audio cues for state feedback."""
from __future__ import annotations

import numpy as np

from .audio_bus import AudioBus
from .config import settings


_SR = settings.sample_rate_out


def _tone(freq_start: float, freq_end: float, duration_ms: int, volume: float = 0.3) -> np.ndarray:
    n = int(_SR * duration_ms / 1000)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    freqs = np.linspace(freq_start, freq_end, n)
    phase = 2 * np.pi * np.cumsum(freqs) / _SR
    samples = np.sin(phase) * volume
    fade = min(int(_SR * 0.008), n // 4)
    if fade > 0:
        samples[:fade] *= np.linspace(0, 1, fade)
        samples[-fade:] *= np.linspace(1, 0, fade)
    return samples.astype(np.float32)


def _silence(ms: int) -> np.ndarray:
    return np.zeros(int(_SR * ms / 1000), dtype=np.float32)


_GENERATORS = {
    "listening_start": lambda: _tone(600, 900, 100),
    "listening_end": lambda: _tone(900, 600, 100),
    "thinking": lambda: _tone(420, 420, 80, 0.15),
    "error": lambda: np.concatenate([_tone(440, 440, 90), _silence(40), _tone(220, 220, 140)]),
    "confirm_required": lambda: np.concatenate(
        [_tone(800, 800, 70), _silence(50), _tone(800, 800, 70)]
    ),
    "ready": lambda: np.concatenate([_tone(500, 700, 80), _silence(20), _tone(700, 900, 100)]),
    "wake": lambda: np.concatenate(
        [_tone(600, 800, 60, 0.4), _silence(30), _tone(800, 1100, 80, 0.4)]
    ),
}


def play(bus: AudioBus, name: str) -> None:
    samples = _GENERATORS[name]()
    pcm = (samples * 32767).clip(-32767, 32767).astype(np.int16).tobytes()
    bus.play_cue(pcm)
