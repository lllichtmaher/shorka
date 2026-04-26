"""Windows UI Automation wrappers using `uiautomation` (yinkaisheng).

Lazy-imported so this module loads in WSL. All functions are sync; callers should
run them in a thread executor if blocking the event loop matters.
"""
from __future__ import annotations

from typing import Any, Optional


_MAX_ITEMS = 40
_MAX_DEPTH = 10
_MAX_TEXT = 2500


def _safe_value(node: Any) -> str:
    """Best-effort text value via ValuePattern → TextPattern → empty."""
    try:
        vp = node.GetValuePattern()
        if vp is not None:
            v = vp.Value
            if v:
                return str(v)
    except Exception:
        pass
    try:
        tp = node.GetTextPattern()
        if tp is not None:
            return tp.DocumentRange.GetText(200)
    except Exception:
        pass
    return ""


def _focused_window() -> Optional[Any]:
    """Walk up from the focused control until we hit a top-level Window."""
    import uiautomation as auto  # type: ignore

    fc = auto.GetFocusedControl()
    if fc is None:
        return None
    node = fc
    for _ in range(20):
        try:
            if node.ControlTypeName == "WindowControl":
                return node
            parent = node.GetParentControl()
            if parent is None:
                return node
            node = parent
        except Exception:
            return node
    return node


def describe_focus() -> str:
    """Short human-readable description of the focused element + window."""
    import uiautomation as auto  # type: ignore

    fc = auto.GetFocusedControl()
    if fc is None:
        return "Nothing is focused."
    name = (fc.Name or "").strip()
    role = (fc.ControlTypeName or "").replace("Control", "")
    val = _safe_value(fc).strip()

    parts: list[str] = []
    if role:
        parts.append(role)
    if name:
        parts.append(f"named '{name}'")
    if val and val != name:
        snippet = val if len(val) <= 60 else val[:57] + "…"
        parts.append(f"value '{snippet}'")

    win = _focused_window()
    win_title = ""
    try:
        if win is not None and win is not fc:
            win_title = (win.Name or "").strip()
    except Exception:
        pass
    suffix = f" in {win_title}" if win_title else ""
    return (", ".join(parts) if parts else "an unidentified element") + suffix


def list_focusable() -> list[dict[str, Any]]:
    """Walk the focused window's UIA tree, return keyboard-focusable nodes."""
    win = _focused_window()
    if win is None:
        return []

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def walk(node: Any, depth: int) -> None:
        if depth > _MAX_DEPTH or len(items) >= _MAX_ITEMS:
            return
        try:
            focusable = bool(node.IsKeyboardFocusable)
        except Exception:
            focusable = False
        if focusable:
            try:
                name = (node.Name or "").strip()
                role = (node.ControlTypeName or "").replace("Control", "")
                key = (name, role)
                if name and key not in seen:
                    seen.add(key)
                    items.append({
                        "name": name,
                        "role": role,
                        "value": _safe_value(node)[:100],
                    })
            except Exception:
                pass
        try:
            children = node.GetChildren()
        except Exception:
            children = []
        for c in children:
            walk(c, depth + 1)

    walk(win, 0)
    return items


def click_by_name(name: str, role: Optional[str] = None) -> bool:
    """Find first focusable element matching name (and optional role) and Invoke/Click it."""
    win = _focused_window()
    if win is None:
        return False

    target_name = name.strip().lower()
    target_role = role.strip().lower() if role else None

    found: list[Any] = []

    def walk(node: Any, depth: int) -> None:
        if depth > _MAX_DEPTH or found:
            return
        try:
            if node.IsKeyboardFocusable:
                n = (node.Name or "").strip().lower()
                r = (node.ControlTypeName or "").replace("Control", "").lower()
                if n == target_name and (target_role is None or r == target_role):
                    found.append(node)
                    return
        except Exception:
            pass
        try:
            for c in node.GetChildren():
                walk(c, depth + 1)
                if found:
                    return
        except Exception:
            pass

    walk(win, 0)
    if not found:
        return False

    target = found[0]
    # Prefer InvokePattern (semantic click); fall back to physical click.
    try:
        ip = target.GetInvokePattern()
        if ip is not None:
            ip.Invoke()
            return True
    except Exception:
        pass
    try:
        target.Click(simulateMove=False)
        return True
    except Exception:
        return False


def read_window_text() -> str:
    """Concatenate all readable text from the focused window's UIA tree."""
    win = _focused_window()
    if win is None:
        return ""
    chunks: list[str] = []
    seen: set[str] = set()

    def walk(node: Any, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        if sum(len(c) for c in chunks) >= _MAX_TEXT:
            return
        try:
            n = (node.Name or "").strip()
            if n and n not in seen:
                seen.add(n)
                chunks.append(n)
            v = _safe_value(node).strip()
            if v and v != n and v not in seen:
                seen.add(v)
                chunks.append(v)
        except Exception:
            pass
        try:
            for c in node.GetChildren():
                walk(c, depth + 1)
        except Exception:
            pass

    walk(win, 0)
    return " · ".join(chunks)[:_MAX_TEXT]


def read_selection() -> str:
    """Return currently selected text via TextPattern's GetSelection."""
    import uiautomation as auto  # type: ignore

    fc = auto.GetFocusedControl()
    if fc is None:
        return ""
    try:
        tp = fc.GetTextPattern()
        if tp is None:
            return ""
        sel = tp.GetSelection()
        if not sel:
            return ""
        return " ".join(s.GetText(500) for s in sel).strip()
    except Exception:
        return ""
