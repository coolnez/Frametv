"""Image preparation for The Frame. Uses Pillow when installed (`pip install .[images]`)."""

from __future__ import annotations

import io

FRAME_SIZE = (3840, 2160)


def sniff_type(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    raise ValueError("downloaded file is not a JPEG or PNG image")


def fit_for_frame(data: bytes) -> tuple[bytes, str]:
    """Downscale anything larger than 4K and re-encode as JPEG; pass through without Pillow."""
    file_type = sniff_type(data)
    try:
        from PIL import Image
    except ImportError:
        return data, file_type

    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.width <= FRAME_SIZE[0] and img.height <= FRAME_SIZE[1] and file_type == "jpg":
                img.verify()
                return data, file_type
            img.draft("RGB", FRAME_SIZE)  # JPEG: decode at reduced scale, keeps memory low on a Pi
            img = img.convert("RGB")
            img.thumbnail(FRAME_SIZE, Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.save(out, "JPEG", quality=92, optimize=True)
    except (OSError, SyntaxError, Image.DecompressionBombError) as exc:
        # Truncated download, corrupt file, or a master too big to decode safely.
        raise ValueError(f"cannot process image: {exc}") from exc
    return out.getvalue(), "jpg"
