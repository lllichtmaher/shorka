"""Screenshot capture for vision-based screen reading."""
from __future__ import annotations

import base64
import io
from typing import Optional


def capture_screenshot(
    bbox: Optional[tuple[int, int, int, int]] = None,
) -> Optional[str]:
    """Capture the screen (or a region) and return as a base64-encoded JPEG.

    Args:
        bbox: Optional (left, top, right, bottom) region. None = full screen.

    Returns:
        Base64-encoded JPEG string, or None on failure.
    """
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        return None

    try:
        img = ImageGrab.grab(bbox=bbox)
        # Resize for faster API calls — 1280px wide is enough for vision models
        max_width = 1280
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            img = img.resize(new_size)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None
