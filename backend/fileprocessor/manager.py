"""Manager for file content extraction (parsing only).

Scope is deliberately narrow: given file bytes + metadata, adapt them into
text/images/tables. No LLM, no agent, no queue, no persistence. Reasoning and
orchestration live on the agent side; this module is exposed to agents through
the ``read_document`` tool.
"""

from __future__ import annotations

import os
from typing import Any

from common.logger import logger
from fileprocessor.models.enums import SupportedFormat
from fileprocessor.models.interface import TabularSheet
from fileprocessor.providers.doc_parser import DocParserAdapter
from fileprocessor.providers.image_passthrough import ImagePassthroughAdapter
from fileprocessor.providers.pdf_parser import PdfParserAdapter
from fileprocessor.providers.sheet_parser import SheetParserAdapter
from fileprocessor.providers.text_parser import TextParserAdapter

# Cap on extracted text handed back to a caller (e.g. the read_document tool), so a
# large document cannot blow the agent's context window / token budget. Overridable via env.
DEFAULT_MAX_TEXT_CHARS = 250_000


class FileprocessorServiceManager:
    """Own format adaptation and file content extraction."""

    def __init__(self, config: Any = None, *dependencies: object) -> None:
        self.config = config
        self.dependencies = list(dependencies)
        self.module_name = "fileprocessor"
        self.adapters = [
            PdfParserAdapter(),
            ImagePassthroughAdapter(),
            DocParserAdapter(),
            SheetParserAdapter(),
            TextParserAdapter(),
        ]

    def extract_content(
        self,
        filename: str,
        content_type: str,
        file_bytes: bytes,
        *,
        max_text_chars: int | None = None,
    ) -> dict[str, object]:
        """Parse file bytes into text/images/tables. Pure, synchronous, no LLM/agent.

        Returns a payload dict with parse_ok/parse_error so the caller can tell an
        unreadable file apart from a genuinely empty one. Never raises on a parse
        failure — the failure is reported in the returned payload.
        """

        effective_filename = filename or "unknown"
        effective_content_type = content_type or "application/octet-stream"

        if not file_bytes:
            logger.warning("extract_content: empty file_bytes for %s", effective_filename)
            return self._failure_payload(
                effective_filename,
                effective_content_type,
                SupportedFormat.UNKNOWN.value,
                "file_bytes is empty",
            )

        adapter = self._resolve_adapter(effective_content_type, effective_filename)
        detected_format = self._detect_format(adapter)
        try:
            payload = adapter.adapt(file_bytes, effective_filename, effective_content_type)
        except Exception as exc:
            logger.warning(
                "extract_content: adapter %s failed for %s: %s",
                adapter.__class__.__name__,
                effective_filename,
                exc,
            )
            return self._failure_payload(
                effective_filename,
                effective_content_type,
                detected_format,
                f"{exc.__class__.__name__}: {exc}",
            )

        cap = self._resolve_max_text_chars(max_text_chars)
        text = str(payload.get("text") or "")
        truncated = len(text) > cap
        if truncated:
            logger.info(
                "extract_content: truncating %s text from %d to %d chars",
                effective_filename,
                len(text),
                cap,
            )
            text = text[:cap]

        return {
            "filename": effective_filename,
            "content_type": effective_content_type,
            "detected_format": detected_format,
            "text": text,
            "images": payload.get("images") or [],
            "tables": payload.get("tables") or [],
            "parse_ok": True,
            "parse_error": None,
            "truncated": truncated,
        }

    def supported_formats(self) -> list[str]:
        return [fmt.value for fmt in SupportedFormat if fmt is not SupportedFormat.UNKNOWN]

    def extract_tabular_sheets(
        self, filename: str, content_type: str, file_bytes: bytes
    ) -> list[TabularSheet]:
        """Return canonical, profiled sheets without sending their rows through an LLM."""
        adapter = self._resolve_adapter(content_type, filename)
        if not isinstance(adapter, SheetParserAdapter):
            raise ValueError(f"'{filename}' is not a supported spreadsheet")
        return adapter.extract_sheets(file_bytes, filename, content_type)

    def extract_spreadsheet_rows(
        self, filename: str, content_type: str, file_bytes: bytes
    ) -> list[TabularSheet]:
        """Compatibility alias for callers using the original spreadsheet API."""
        return self.extract_tabular_sheets(filename, content_type, file_bytes)

    @staticmethod
    def _failure_payload(
        filename: str, content_type: str, detected_format: str, error: str
    ) -> dict[str, object]:
        return {
            "filename": filename,
            "content_type": content_type,
            "detected_format": detected_format,
            "text": "",
            "images": [],
            "tables": [],
            "parse_ok": False,
            "parse_error": error,
            "truncated": False,
        }

    @staticmethod
    def _resolve_max_text_chars(override: int | None) -> int:
        if override is not None and override > 0:
            return override
        try:
            configured = int(os.getenv("FILEPROCESSOR_MAX_TEXT_CHARS", str(DEFAULT_MAX_TEXT_CHARS)))
        except (TypeError, ValueError):
            return DEFAULT_MAX_TEXT_CHARS
        return configured if configured > 0 else DEFAULT_MAX_TEXT_CHARS

    def _resolve_adapter(self, content_type: str, filename: str):
        for adapter in self.adapters:
            if adapter.supports(content_type, filename):
                return adapter
        return TextParserAdapter()

    @staticmethod
    def _detect_format(adapter) -> str:
        name = adapter.__class__.__name__.lower()
        if "pdf" in name:
            return SupportedFormat.PDF.value
        if "image" in name:
            return SupportedFormat.IMAGE.value
        if "doc" in name:
            return SupportedFormat.DOC.value
        if "sheet" in name:
            return SupportedFormat.SHEET.value
        if "text" in name:
            return SupportedFormat.TEXT.value
        return SupportedFormat.UNKNOWN.value
