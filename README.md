## VoiceCtl

A voice-controlled computer for blind users. Speak naturally; the assistant interprets intent, executes actions on Windows, and narrates everything as it goes — because the user can't see the screen.

Built for LA Hacks 2026.

## What it does

- **Wake word + active session** — say "Hey Shorka" to wake; phrases like "stop", "go away", "never mind", "goodbye", "go to sleep" dismiss back to idle. Active sessions also auto-dismiss after 60s of silence.
- **Streaming end-to-end** — silero-vad utterance endpointing → OpenAI (or Groq) STT → Claude Sonnet 4.6 streaming → ElevenLabs WebSocket TTS.
- **Barge-in** — start talking and the assistant stops mid-sentence; in-flight tool calls are repaired so the conversation history stays valid for the next turn.
- **Switchable voices** — "switch to the British voice" works via fuzzy alias matching. Bundled profiles: Rachel, Antoni, Daniel, Bella, Adam (edit `data/voices.json` to add more).
- **Launch apps, type, browse, read screen** — Windows automation via UIA + pywinauto, plus keyboard-first navigation.
- **Vision tools** — `see_screen` describes the whole screen, `find_on_screen` locates a specific element. Both go through GPT-4o-mini for blind-friendly prose.
- **Constant narration** — every action is announced before, during, and after.
- **Safety** — dangerous tools are gated by spoken yes/no confirmation with a 10s timeout and up to two re-prompts.
- **Undo** — "undo that" reverses reversible actions (e.g. close a launched app); tools register a revert handler when applicable.
- **Flutter overlay** — small always-on-top orb that mirrors live state (idle / listening / speaking / awaiting confirm / offline) and lets you toggle the mic, switch voice, pick a screen corner, and see the transcript.

## Setup

**Run on Windows host** (not WSL — no audio device).

1. Install Python 3.13 from python.org.
2. Clone this repo onto the Windows side at e.g. `C:\Users\<you>\Downloads\lahacks26-2`.
3. Copy `.env.example` to `.env` and fill in:
   - `ANTHROPIC_API_KEY` — from console.anthropic.com
   - `OPENAI_API_KEY` — from platform.openai.com (used for Whisper STT)
   - `ELEVENLABS_API_KEY` — from elevenlabs.io
4. From PowerShell in the project dir: `.\run_windows.ps1`

First run installs the venv (~3-5 min). Subsequent runs start in seconds.

## Switching voices

Edit `data/voices.json` to add ElevenLabs voice IDs and friendly names. The `aliases` array enables fuzzy matches like "the British voice" → daniel.

## Optional: Flutter overlay

A small frame-less Flutter window pins to a screen corner and shows live status: listening / speaking / awaiting confirmation, the conversation transcript, and a voice picker. The backend exposes a tiny HTTP API on `127.0.0.1:8412` (`/status`, `/transcript`, `/voices`, `/toggle-listen`, `/set-voice`, `/dismiss`) that the overlay polls.

Run from `frontend/`:

```bash
flutter pub get
flutter run -d windows
```

The overlay launches even if the backend isn't running — tap the orb to start `app.main`.

## Architecture

See `app/` directory layout:

- `audio_bus.py` — single sounddevice owner; arbitrates record/play; mixes TTS + cues.
- `listener.py` — silero-vad on mic chunks → utterance buffer → STT, with idle/active gating.
- `wake_word.py` — fuzzy "Shorka" detection + dismiss phrases.
- `stt.py` — OpenAI (or Groq) transcription client.
- `narrator.py` — ElevenLabs WebSocket streaming TTS with interrupt.
- `voices.py` — voice profile loader with rapidfuzz match.
- `cues.py` — short tones for non-verbal state feedback.
- `brain.py` — Claude streaming + tool-use loop with message-history repair on barge-in.
- `tools/` — apps, keyboard, screen, vision, voice, web, history, confirm.
- `middleware/confirm.py` — spoken yes/no gate for dangerous tools.
- `os_layer/` — Windows automation primitives (uiautomation, pywinauto, screenshot, OCR).
- `api_server.py` — HTTP control API for the Flutter overlay.

Frontend (`frontend/lib/main.dart`):

- Animated orb that reflects state (idle / listening / speaking / awaiting confirm / offline).
- Expandable panel with transcript bubbles, status pill, and primary mic toggle.
- Settings: voice picker, screen-corner picker, about.

Full design notes: `/home/<you>/.claude/plans/create-an-app-that-shimmering-scone.md`.

## Develop in WSL, run on Windows

The Windows-only deps (`uiautomation`, `pywinauto`, `winsdk`, `pyautogui`) won't install in WSL. For editing/linting in WSL:

```bash
cd /mnt/c/Users/<you>/Downloads/lahacks26-2
python3 -m venv .venv-wsl
source .venv-wsl/bin/activate
pip install -e ".[dev]"  # without [windows] extra
```

For the actual runtime, use `run_windows.ps1` from a PowerShell terminal.
