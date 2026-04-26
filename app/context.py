"""Process-wide singletons that tools can reach without circular imports.

`main.py` calls `init(...)` once at startup. Tools that need narrator/session/voices/bus
import this module and read attributes. Tools that don't need them ignore it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .audio_bus import AudioBus
    from .narrator import Narrator
    from .session import Session
    from .voices import Voices


narrator: Optional["Narrator"] = None
session: Optional["Session"] = None
voices: Optional["Voices"] = None
audio_bus: Optional["AudioBus"] = None


def init(
    narrator_: "Narrator",
    session_: "Session",
    voices_: "Voices",
    audio_bus_: "AudioBus",
) -> None:
    global narrator, session, voices, audio_bus
    narrator = narrator_
    session = session_
    voices = voices_
    audio_bus = audio_bus_
