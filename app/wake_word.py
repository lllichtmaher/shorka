"""Wake word detection and dismiss detection for 'Shorka'.

Uses fuzzy matching so that variations like 'hey shorka', 'shorka', 'shorca',
'sure ka', etc. all trigger activation.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz


WAKE_WORD = "shorka"

# Phonetic / spelling variants people might say
_ALIASES = [
    "shorka", "shorca", "shorca", "shurka", "shourka",
    "sure ka", "shore ka", "shorke", "shorko", "shor ka",
    "chorka", "шорка",
]

# Minimum fuzzy similarity score (0-100) for a word to count as the wake word.
_THRESHOLD = 65

# Phrases that dismiss the assistant back to idle
_DISMISS_PHRASES = [
    "shut up",
    "go away",
    "stop listening",
    "stop responding",
    "please stop",
    "go to sleep",
    "goodbye",
    "good bye",
    "bye bye",
    "bye shorka",
    "that's all",
    "thats all",
    "that is all",
    "nevermind",
    "never mind",
    "dismiss",
    "sleep",
    "stop",
    "be quiet",
    "quiet",
    "leave me alone",
    "i'm done",
    "im done",
]


def detect(text: str) -> tuple[bool, str]:
    """Check if text contains the wake word.

    Returns (detected: bool, remaining_text: str).
    If the wake word is found, remaining_text is the text with the wake word
    and common prefixes ('hey', 'yo', etc.) stripped out.
    """
    lower = text.lower().strip()
    if not lower:
        return False, ""

    # Try matching each word and bigram against the wake word + aliases
    words = lower.split()
    wake_idx_start = -1
    wake_idx_end = -1

    # Check single words
    for i, word in enumerate(words):
        clean = re.sub(r"[^a-z]", "", word)
        if not clean:
            continue
        if _is_wake(clean):
            wake_idx_start = i
            wake_idx_end = i + 1
            break

    # Check bigrams (e.g. "sure ka" → "sureka" ≈ "shorka")
    if wake_idx_start == -1:
        for i in range(len(words) - 1):
            bigram = re.sub(r"[^a-z]", "", words[i]) + re.sub(r"[^a-z]", "", words[i + 1])
            if _is_wake(bigram):
                wake_idx_start = i
                wake_idx_end = i + 2
                break

    if wake_idx_start == -1:
        return False, ""

    # Everything after the wake word is the command
    remaining_words = words[wake_idx_end:]
    remaining = " ".join(remaining_words).strip()

    return True, remaining


def is_dismiss(text: str) -> bool:
    """Check if the text is a dismiss command to put the assistant back to sleep."""
    lower = text.lower().strip()
    if not lower:
        return False

    for phrase in _DISMISS_PHRASES:
        if phrase in lower:
            return True

    # Fuzzy check for short utterances that might be garbled versions of dismiss phrases
    if len(lower.split()) <= 3:
        for phrase in _DISMISS_PHRASES:
            if fuzz.ratio(lower, phrase) >= 75:
                return True

    return False


def _is_wake(candidate: str) -> bool:
    """Check if a candidate string fuzzy-matches the wake word or its aliases."""
    for alias in _ALIASES:
        score = fuzz.ratio(candidate, alias.replace(" ", ""))
        if score >= _THRESHOLD:
            return True
    return False
