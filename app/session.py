"""Per-process conversation state."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass
class ActionRecord:
    timestamp: float
    tool_name: str
    tool_input: dict
    result: dict
    revert: Optional[Callable[[], Awaitable[None]]] = None


@dataclass
class TranscriptLine:
    """A single line of dialog for the UI overlay."""
    role: str  # "user" | "assistant" | "tool"
    text: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class Session:
    messages: list[dict] = field(default_factory=list)
    current_voice_id: str = ""
    current_voice_key: str = ""
    # Future is set by middleware/confirm; main.py routes the next utterance into it.
    pending_confirmation: Optional[Any] = None  # asyncio.Future[str]
    interrupted: bool = False
    history: deque[ActionRecord] = field(default_factory=lambda: deque(maxlen=50))
    # Last ~20 lines of dialog for the Flutter overlay to display.
    transcript: deque[TranscriptLine] = field(default_factory=lambda: deque(maxlen=20))
    # A tool can set this immediately before returning. Brain captures it as the
    # revert handler for the action it just performed, then clears it.
    last_revert: Optional[Callable[[], Awaitable[None]]] = None

    def add_transcript(self, role: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.transcript.append(TranscriptLine(role=role, text=text))

    def add_history(
        self,
        tool_name: str,
        tool_input: dict,
        result: Any,
        revert: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> None:
        result_dict = result if isinstance(result, dict) else {"value": result}
        self.history.append(
            ActionRecord(
                timestamp=time.time(),
                tool_name=tool_name,
                tool_input=tool_input,
                result=result_dict,
                revert=revert,
            )
        )

    def last_assistant_text(self) -> str:
        for msg in reversed(self.messages):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", [])
            if isinstance(content, str):
                return content
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
        return ""
