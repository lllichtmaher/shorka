"""VoiceCtl entry point.

Wires AudioBus, Listener (silero-vad + STT), Narrator (ElevenLabs WS TTS),
Brain (Claude streaming + tool-use), the always-on barge-in loop, and the
HTTP API for the Flutter frontend.
"""
from __future__ import annotations

import asyncio
import sys

from . import api_server, context, cues
from .audio_bus import AudioBus
from .brain import Brain
from .config import settings
from .listener import DismissEvent, Listener, Utterance
from .narrator import Narrator
from .session import Session
from .voices import Voices


async def amain() -> None:
    bus = AudioBus()
    bus.start()

    voices = Voices.load(settings.voices_path)
    voice = voices.default()
    narrator = Narrator(bus, voice.id)

    session = Session(current_voice_id=voice.id, current_voice_key=voice.key)
    context.init(narrator, session, voices, bus)
    brain = Brain(narrator, session)
    brain_task: asyncio.Task | None = None

    async def cancel_brain() -> None:
        nonlocal brain_task
        if brain_task is not None and not brain_task.done():
            brain_task.cancel()
            try:
                await brain_task
            except (asyncio.CancelledError, Exception):
                pass
        brain_task = None

    async def on_speech_start() -> None:
        # Barge-in: stop narration immediately. Don't kill the brain task if a
        # confirmation prompt is pending — it needs to receive the next utterance.
        if narrator.is_speaking:
            await narrator.interrupt()
        if session.pending_confirmation is None:
            await cancel_brain()
        session.interrupted = True

    listener = Listener(bus, on_speech_start=on_speech_start)
    # Expose listener on context so the API server can read its state
    context._listener = listener  # type: ignore[attr-defined]

    # --- API server callbacks ---
    async def toggle_listen() -> None:
        """Toggle between IDLE and ACTIVE from the Flutter mic button."""
        if listener.is_active:
            # Dismiss
            cues.play(bus, "listening_end")
            listener._deactivate()
            await cancel_brain()
            await narrator.interrupt()
            await narrator.say("Going to sleep.")
        else:
            # Activate
            cues.play(bus, "wake")
            listener._activate()
            await narrator.say("Hey! What can I do for you?")

    async def force_dismiss() -> None:
        """Dismiss from the Flutter UI."""
        if listener.is_active:
            cues.play(bus, "listening_end")
            listener._deactivate()
        await cancel_brain()
        await narrator.interrupt()

    api_server.set_callbacks(
        on_toggle_listen=toggle_listen,
        on_force_dismiss=force_dismiss,
    )
    await api_server.start()

    print(f"[main] voice: {voice.name} ({voice.id})", file=sys.stderr)
    print(f"[main] model: {settings.claude_model}", file=sys.stderr)
    cues.play(bus, "ready")
    await asyncio.sleep(0.2)
    await narrator.say(
        f"Voice assistant ready. I'm using {voice.name}'s voice. "
        f"Say 'Hey Shorka' to wake me up, then tell me what you need."
    )

    try:
        async for event in listener.utterances():
            if isinstance(event, DismissEvent):
                # User dismissed Shorka
                await cancel_brain()
                await narrator.interrupt()
                await narrator.say("Okay, going to sleep. Say 'Hey Shorka' when you need me.")
                continue

            utt = event
            assert isinstance(utt, Utterance)

            # If we just activated (wake word with no command), greet the user
            if not utt.text:
                continue

            print(f"[user] {utt.text}", file=sys.stderr)
            session.add_transcript("user", utt.text)
            pending = session.pending_confirmation
            if pending is not None and not pending.done():
                pending.set_result(utt.text)
                continue
            await cancel_brain()
            brain_task = asyncio.create_task(brain.handle(utt.text))
    finally:
        await cancel_brain()
        await narrator.interrupt()
        await api_server.stop()
        bus.stop()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        print("\n[main] bye.", file=sys.stderr)


if __name__ == "__main__":
    main()
