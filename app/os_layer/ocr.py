"""OCR fallback via Tesseract (optional install).

We try Windows.Media.Ocr first via winsdk if available (faster, GPU-accelerated,
ships with Windows). Falls back to pytesseract if winsdk isn't installed.
Returns empty string if neither is available.
"""
from __future__ import annotations

from typing import Optional


def screenshot_ocr(bbox: Optional[tuple[int, int, int, int]] = None) -> str:
    """OCR a screen region. bbox is (left, top, right, bottom) or None for full screen."""
    try:
        from PIL import ImageGrab  # type: ignore
    except ImportError:
        return ""
    try:
        img = ImageGrab.grab(bbox=bbox)
    except Exception:
        return ""

    text = _try_winsdk(img)
    if text:
        return text
    return _try_tesseract(img)


def _try_winsdk(img) -> str:  # noqa: ANN001
    try:
        import asyncio
        import io

        from winsdk.windows.graphics.imaging import BitmapDecoder  # type: ignore
        from winsdk.windows.media.ocr import OcrEngine  # type: ignore
        from winsdk.windows.storage.streams import (  # type: ignore
            DataWriter,
            InMemoryRandomAccessStream,
        )
    except ImportError:
        return ""

    async def _ocr() -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream.get_output_stream_at(0))
        writer.write_bytes(png_bytes)
        await writer.store_async()
        await writer.flush_async()
        writer.detach_stream()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()

        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return ""
        result = await engine.recognize_async(bitmap)
        return (result.text or "").strip()

    try:
        return asyncio.run(_ocr())
    except Exception:
        return ""


def _try_tesseract(img) -> str:  # noqa: ANN001
    try:
        import pytesseract  # type: ignore
    except ImportError:
        return ""
    try:
        return (pytesseract.image_to_string(img) or "").strip()
    except Exception:
        return ""
