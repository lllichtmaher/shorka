"""Window enumeration and focus via pywinauto.

Lazy-imports pywinauto so this module is importable in WSL.
"""
from __future__ import annotations

from typing import Any


def list_windows() -> list[dict[str, Any]]:
    """Return visible top-level windows: [{title, handle}]."""
    from pywinauto import Desktop  # type: ignore

    out: list[dict[str, Any]] = []
    for w in Desktop(backend="uia").windows():
        try:
            title = w.window_text()
            if not title:
                continue
            if not w.is_visible():
                continue
            out.append({"title": title, "handle": w.handle})
        except Exception:
            continue
    return out


def _match_window(title_query: str) -> dict[str, Any] | None:
    from rapidfuzz import fuzz, process  # type: ignore

    windows = list_windows()
    if not windows:
        return None
    titles = [w["title"] for w in windows]
    match = process.extractOne(title_query, titles, scorer=fuzz.WRatio, score_cutoff=50)
    if match is None:
        return None
    return next(w for w in windows if w["title"] == match[0])


def focus_window(title_query: str) -> dict[str, Any]:
    """Bring a window matching `title_query` to the foreground (fuzzy)."""
    from pywinauto import Desktop  # type: ignore

    target = _match_window(title_query)
    if target is None:
        wins = list_windows()
        return {
            "ok": False,
            "error": f"no window matches '{title_query}'",
            "available": [w["title"] for w in wins[:5]],
        }
    try:
        d = Desktop(backend="uia").window(handle=target["handle"])
        try:
            d.restore()
        except Exception:
            pass
        d.set_focus()
        return {"ok": True, "focused": target["title"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def close_window(title_query: str) -> dict[str, Any]:
    """Close a window matching `title_query` (fuzzy). Best-effort; some apps prompt to save."""
    from pywinauto import Desktop  # type: ignore

    target = _match_window(title_query)
    if target is None:
        return {"ok": False, "error": f"no window matches '{title_query}'"}
    try:
        d = Desktop(backend="uia").window(handle=target["handle"])
        d.close()
        return {"ok": True, "closed": target["title"]}
    except Exception as e:
        return {"ok": False, "error": str(e)}
