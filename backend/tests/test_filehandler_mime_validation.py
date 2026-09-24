from __future__ import annotations

import io
import os
import zipfile

import pytest

from exceptions import ValidationError
from filehandler.db_models import FilehandlerModelService
from filehandler.manager import FilehandlerServiceManager

# STAT-356: DOCX/XLSX uploads were rejected because MIME detection ran over only
# the first 2048 bytes, so libmagic never saw the ZIP central directory at the end
# of the OOXML container and misreported the type. These tests exercise the fix
# (full-bytes detection + OOXML aliases) directly against the validator.


def _manager() -> FilehandlerServiceManager:
    return FilehandlerServiceManager(FilehandlerModelService(database_service_manager=None), None, None)


def _requires_magic() -> None:
    try:
        import magic  # noqa: F401
    except ImportError:
        pytest.skip("python-magic not available; MIME validation is soft-skipped")


def _docx_bytes() -> bytes:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    # Pad the body so the file exceeds the old 2048-byte detection window and the
    # ZIP central directory lands well past it — the exact case the bug missed.
    for _ in range(200):
        document.add_paragraph("Candidate resume content used to grow the DOCX payload.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _xlsx_bytes() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in range(1, 300):
        sheet.append([f"value-{row}", row])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_validate_mime_accepts_large_docx() -> None:
    _requires_magic()
    payload = _docx_bytes()
    assert len(payload) > FilehandlerServiceManager._MIME_DETECTION_HEADER_BYTES
    # Must not raise: full-bytes detection identifies the OOXML/ZIP container.
    _manager()._validate_mime_type(payload, [".docx"])


def test_validate_mime_accepts_large_xlsx() -> None:
    _requires_magic()
    payload = _xlsx_bytes()
    assert len(payload) > FilehandlerServiceManager._MIME_DETECTION_HEADER_BYTES
    _manager()._validate_mime_type(payload, [".xlsx"])


def test_validate_mime_rejects_mismatched_type() -> None:
    _requires_magic()
    # A DOCX payload declared as a PNG must still be rejected — the fix widens
    # OOXML acceptance, it does not disable the anti-spoof check.
    with pytest.raises(ValidationError):
        _manager()._validate_mime_type(_docx_bytes(), [".png"])


def test_validate_mime_rejects_plain_zip_declared_as_docx() -> None:
    # The application/zip and application/octet-stream aliases exist only for
    # real OOXML files libmagic can't specifically identify — a plain,
    # non-Office zip archive uploaded as .docx must still be rejected.
    _requires_magic()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")
    with pytest.raises(ValidationError):
        _manager()._validate_mime_type(buffer.getvalue(), [".docx"])


def test_validate_mime_rejects_arbitrary_binary_declared_as_xlsx() -> None:
    # Unrecognized binary content (libmagic reports application/octet-stream)
    # must not be accepted just because that generic mime is in the allowlist.
    _requires_magic()
    with pytest.raises(ValidationError):
        _manager()._validate_mime_type(os.urandom(4096), [".xlsx"])


def test_is_ooxml_zip_true_for_real_docx_false_for_plain_zip_and_garbage() -> None:
    assert FilehandlerServiceManager._is_ooxml_zip(_docx_bytes()) is True

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "hello")
    assert FilehandlerServiceManager._is_ooxml_zip(buffer.getvalue()) is False

    assert FilehandlerServiceManager._is_ooxml_zip(os.urandom(4096)) is False


# FT-0192: an org allowing .html could never upload one. The extension-to-MIME
# map had no HTML entry, so a real HTML file's `text/html` was never in the
# allowed set whenever .html sat alongside a mapped extension.

_HTML_DOC = (
    b"<!DOCTYPE html>\n<html lang=\"en\"><head><title>Report</title></head>"
    b"<body><h1>Quarterly</h1><p>Contents</p></body></html>\n"
)
_XHTML_DOC = (
    b"<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
    b"<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.0 Strict//EN\" "
    b"\"http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd\">\n"
    b"<html xmlns=\"http://www.w3.org/1999/xhtml\"><body><p>x</p></body></html>\n"
)


@pytest.mark.parametrize(
    "allowed",
    [
        [".html"],
        # The combinations that failed before: any mapped extension alongside
        # .html made the allowed-MIME set non-empty, so text/html was rejected.
        [".html", ".pdf"],
        [".html", ".txt"],
        [".html", ".docx", ".csv"],
    ],
)
def test_validate_mime_accepts_html_for_html_extension(allowed: list[str]) -> None:
    _requires_magic()
    # Must not raise.
    _manager()._validate_mime_type(_HTML_DOC, allowed)


def test_validate_mime_accepts_htm_extension_like_html() -> None:
    _requires_magic()
    _manager()._validate_mime_type(_HTML_DOC, [".htm", ".pdf"])


def test_validate_mime_accepts_xhtml_served_as_html() -> None:
    # libmagic reports XHTML as application/xhtml+xml, and such files are
    # normally saved with a .html/.htm extension.
    _requires_magic()
    _manager()._validate_mime_type(_XHTML_DOC, [".html"])
    _manager()._validate_mime_type(_XHTML_DOC, [".htm"])


def test_validate_mime_rejects_non_html_declared_as_html() -> None:
    # Adding HTML widens acceptance for real HTML only; the anti-spoof check
    # still applies. Plain text is included deliberately: it is what libmagic
    # reports for a structureless file, and accepting it would let any text
    # file through as .html.
    _requires_magic()
    manager = _manager()
    with pytest.raises(ValidationError):
        manager._validate_mime_type(b"%PDF-1.4\n1 0 obj\n<< >>\nendobj\n%%EOF\n", [".html"])
    with pytest.raises(ValidationError):
        manager._validate_mime_type(b"just some plain text, not markup\n", [".html"])


def test_validate_mime_html_change_does_not_affect_other_types() -> None:
    # AC3: the map is keyed by extension, so other types are untouched. An HTML
    # file offered where only .pdf/.txt is allowed must still be rejected.
    _requires_magic()
    manager = _manager()
    with pytest.raises(ValidationError):
        manager._validate_mime_type(_HTML_DOC, [".pdf"])
    with pytest.raises(ValidationError):
        manager._validate_mime_type(_HTML_DOC, [".txt"])
    # And a plain text file is still accepted for .txt.
    manager._validate_mime_type(b"plain text body\n", [".txt"])
