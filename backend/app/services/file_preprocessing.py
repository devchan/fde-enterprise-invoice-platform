"""Pre-extraction file preprocessing.

Vision-token cost for image invoices scales with pixel count, and phone
photos/scans routinely arrive at 4000px+ where ~2000px reads identically for
extraction. Downscale oversized JPEG/PNG uploads before sending them to the
provider. Deliberately conservative: only the bytes sent to the extractor are
resized — the stored original is never modified — and any failure (missing
Pillow, corrupt image) returns the original bytes so preprocessing can never
break extraction.
"""

import io

import structlog

from app.core.config import settings

logger = structlog.get_logger("app.services.file_preprocessing")

_RESIZABLE_MIME_TYPES = {"image/jpeg", "image/png"}


def preprocess_for_extraction(*, file_bytes: bytes, mime_type: str | None) -> bytes:
    max_dimension = settings.extraction_image_max_dimension
    if max_dimension <= 0 or mime_type not in _RESIZABLE_MIME_TYPES:
        return file_bytes

    try:
        from PIL import Image
    except ImportError:
        return file_bytes

    try:
        image = Image.open(io.BytesIO(file_bytes))
        width, height = image.size
        if max(width, height) <= max_dimension:
            return file_bytes

        scale = max_dimension / max(width, height)
        resized = image.resize((max(int(width * scale), 1), max(int(height * scale), 1)))
        buffer = io.BytesIO()
        if mime_type == "image/jpeg":
            # JPEG can't carry alpha; flatten any odd source mode first.
            if resized.mode not in ("RGB", "L"):
                resized = resized.convert("RGB")
            resized.save(buffer, format="JPEG", quality=85)
        else:
            resized.save(buffer, format="PNG")
        downscaled = buffer.getvalue()
        # A pathological image could re-encode larger than the original; keep
        # whichever payload is actually smaller.
        if len(downscaled) >= len(file_bytes):
            return file_bytes

        logger.info(
            "file_preprocessing.image_downscaled",
            original_bytes=len(file_bytes),
            downscaled_bytes=len(downscaled),
            original_size=f"{width}x{height}",
            max_dimension=max_dimension,
        )
        return downscaled
    except Exception as exc:
        logger.warning("file_preprocessing.failed", error_message=str(exc))
        return file_bytes
