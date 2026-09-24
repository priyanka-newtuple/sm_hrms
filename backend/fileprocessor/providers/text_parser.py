"""Text adapter for plain text files."""

from __future__ import annotations


class TextParserAdapter:
    """Adapter for text-like payloads."""

    _MIME_PREFIXES = ("text/", "application/json")

    def supports(self, content_type: str, filename: str) -> bool:
        lower_name = filename.lower()
        return content_type.startswith(self._MIME_PREFIXES) or lower_name.endswith(
            (".txt", ".md", ".json")
        )

    def adapt(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, object]:
        text = file_bytes.decode("utf-8", errors="replace")
        return {
            "adapter": "text",
            "filename": filename,
            "content_type": content_type,
            "text": text,
            "images": [],
            "tables": [],
        }
