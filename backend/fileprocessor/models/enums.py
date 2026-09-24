"""Enums for fileprocessor runtime."""

from __future__ import annotations

from common.data_model import ExtendedStrEnum


class SupportedFormat(ExtendedStrEnum):
    PDF = "pdf"
    IMAGE = "image"
    DOC = "doc"
    SHEET = "sheet"
    TEXT = "text"
    UNKNOWN = "unknown"
