"""Image adapter: images go to the vision model directly, they are not OCR'd.

Images are attached to the agent run's input as a multimodal ``input_image`` block
by the agent runtime, so a vision-capable model reads them directly. The
fileprocessor no longer performs OCR on images (no pytesseract). This adapter only
classifies the file as an image and returns **no text** — it deliberately does not
author any model-facing instruction (that belongs in the agent service, not the
fileprocessor). ``read_document`` on an image therefore returns empty text plus a
``detected_format`` of ``image``, so the caller can tell it apart from an empty file.
"""

from __future__ import annotations

from typing import ClassVar


class ImagePassthroughAdapter:
    """Adapter for image files (no OCR; the vision-model input carries the content)."""

    _IMAGE_MIMES: ClassVar[set[str]] = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/tiff",
        "image/gif",
    }

    def supports(self, content_type: str, filename: str) -> bool:
        return content_type in self._IMAGE_MIMES or filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".gif")
        )

    def adapt(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, object]:
        _ = file_bytes  # bytes are delivered to the model via the vision input, not here
        return {
            "adapter": "image",
            "filename": filename,
            "content_type": content_type,
            "text": "",
            "images": [],
            "tables": [],
        }
