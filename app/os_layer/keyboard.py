"""Keyboard input via pyautogui. Lazy-imported to keep WSL happy."""
from __future__ import annotations


def type_text(text: str, interval: float = 0.01) -> None:
    """Type `text` into the currently focused window (ASCII-printable chars)."""
    import pyautogui  # type: ignore

    # pyautogui.write accepts ASCII-printable chars + a few specials.
    pyautogui.write(text, interval=interval)


def press_keys(combo: str) -> None:
    """Press a key or combo. Examples: 'enter', 'ctrl+s', 'alt+tab', 'ctrl+shift+t'."""
    import pyautogui  # type: ignore

    keys = [k.strip().lower() for k in combo.split("+") if k.strip()]
    if not keys:
        raise ValueError(f"empty key combo: {combo!r}")
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)
