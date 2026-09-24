"""Images are vision-only now: the fileprocessor no longer OCRs them (STAT-254).

The ImageOcrAdapter (pytesseract) was removed; ImagePassthroughAdapter classifies
image files and returns a short guidance notice instead of OCR text, so
read_document degrades gracefully and points the agent at the image input.
"""

from __future__ import annotations

from fileprocessor.manager import FileprocessorServiceManager
from fileprocessor.models.enums import SupportedFormat
from fileprocessor.providers.image_passthrough import ImagePassthroughAdapter


def test_image_passthrough_supports_common_image_types() -> None:
    adapter = ImagePassthroughAdapter()
    assert adapter.supports("image/png", "x.png")
    assert adapter.supports("image/jpeg", "x.jpg")
    assert adapter.supports("", "photo.JPG")  # by extension, case-insensitive
    assert adapter.supports("image/webp", "x.webp")
    assert not adapter.supports("application/pdf", "resume.pdf")
    assert not adapter.supports("text/plain", "notes.txt")


def test_extract_content_on_image_returns_empty_text_no_ocr_no_instruction() -> None:
    fp = FileprocessorServiceManager()
    out = fp.extract_content("resume.png", "image/png", b"\x89PNG\r\n\x1a\n not-really-decodable")
    assert out["detected_format"] == SupportedFormat.IMAGE.value
    assert out["parse_ok"] is True
    # No OCR text and NO model-facing instruction — the fileprocessor stays neutral;
    # the image is delivered to the model via the vision input, not through read_document.
    assert out["text"] == ""
    assert out["images"] == []


def test_extract_content_on_image_never_raises_without_tesseract() -> None:
    # Regression: previously this went through pytesseract and blew up when
    # tesseract was not installed. It must now succeed with a graceful payload.
    fp = FileprocessorServiceManager()
    out = fp.extract_content("photo.jpeg", "image/jpeg", b"\xff\xd8\xff\xe0 garbage jpeg bytes")
    assert out["parse_ok"] is True
    assert out["detected_format"] == SupportedFormat.IMAGE.value
