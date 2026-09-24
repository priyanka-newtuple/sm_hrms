"""Unit tests for FileprocessorServiceManager.extract_content (parsing only)."""

from __future__ import annotations

import io

import pytest

from fileprocessor.manager import FileprocessorServiceManager


def _manager() -> FileprocessorServiceManager:
    return FileprocessorServiceManager(config=None)


def _docx_bytes_from(builder) -> bytes:
    docx = pytest.importorskip("docx")
    document = docx.Document()
    builder(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_extract_text_file() -> None:
    result = _manager().extract_content("notes.txt", "text/plain", b"hello world")
    assert result["parse_ok"] is True
    assert result["detected_format"] == "text"
    assert result["text"] == "hello world"
    assert result["truncated"] is False


def test_extract_csv_produces_tables_and_text() -> None:
    csv_bytes = b"name,role\nJane,Engineer\nJohn,Manager\n"
    result = _manager().extract_content("people.csv", "text/csv", csv_bytes)
    assert result["parse_ok"] is True
    assert result["detected_format"] == "sheet"
    assert result["tables"] == [
        {"name": "Jane", "role": "Engineer"},
        {"name": "John", "role": "Manager"},
    ]
    assert "Jane" in result["text"]


def test_extract_tabular_sheets_returns_complete_profiled_csv_not_preview_cap() -> None:
    csv_bytes = ("row,name\n" + "".join(f"{index},Person {index}\n" for index in range(250))).encode()

    sheets = _manager().extract_tabular_sheets("people.csv", "text/csv", csv_bytes)

    assert len(sheets) == 1
    assert [column.name for column in sheets[0].columns] == ["row", "name"]
    assert sheets[0].columns[0].inferred_type == "integer"
    assert sheets[0].columns[1].sample_values == ["Person 0", "Person 1", "Person 2"]
    assert len(sheets[0].rows) == 250
    assert sheets[0].rows[-1].source_row_number == 250
    assert sheets[0].rows[-1].values == {"row": 249, "name": "Person 249"}


def test_extract_tabular_sheets_preserves_workbook_sheets_and_row_coordinates() -> None:
    pandas = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    workbook = io.BytesIO()
    with pandas.ExcelWriter(workbook, engine="openpyxl") as writer:
        pandas.DataFrame([{"name": "Lamp"}]).to_excel(
            writer, sheet_name="Products", index=False
        )
        pandas.DataFrame([{"name": "Desk"}, {"name": "Chair"}]).to_excel(
            writer, sheet_name="Furniture", index=False
        )

    sheets = _manager().extract_tabular_sheets(
        "catalog.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        workbook.getvalue(),
    )

    assert [sheet.sheet_name for sheet in sheets] == ["Products", "Furniture"]
    assert [sheet.row_count for sheet in sheets] == [1, 2]
    assert [row.source_row_number for row in sheets[1].rows] == [1, 2]


def test_empty_bytes_reported_as_parse_failure() -> None:
    result = _manager().extract_content("x.pdf", "application/pdf", b"")
    assert result["parse_ok"] is False
    assert result["parse_error"] == "file_bytes is empty"
    assert result["text"] == ""


def test_corrupt_pdf_reported_as_parse_failure_not_garbage() -> None:
    # Not a real PDF — the adapter must raise and extract_content must surface it,
    # rather than silently returning empty/garbage text.
    result = _manager().extract_content("broken.pdf", "application/pdf", b"%PDF-not-really")
    assert result["parse_ok"] is False
    assert result["parse_error"]
    assert result["text"] == ""
    assert result["detected_format"] == "pdf"


def test_text_is_truncated_to_cap() -> None:
    big = b"a" * 100
    result = _manager().extract_content("big.txt", "text/plain", big, max_text_chars=10)
    assert result["parse_ok"] is True
    assert result["truncated"] is True
    assert result["text"] == "a" * 10


def test_docx_extracts_text_from_table_only_body() -> None:
    # STAT-356 follow-up: real-world resume/report .docx templates commonly lay
    # their entire body out inside a table (two-column layout), not paragraphs.
    # DocParserAdapter used to read only doc.paragraphs, so these documents
    # extracted as empty text — the agent then had nothing to extract fields
    # from and never called create_entity.
    def _build(document):
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = "Lauren Chen"
        table.rows[0].cells[1].text = "lauren.chen@example.com"

    payload = _docx_bytes_from(_build)
    result = _manager().extract_content(
        "resume.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        payload,
    )
    assert result["parse_ok"] is True
    assert "Lauren Chen" in result["text"]
    assert "lauren.chen@example.com" in result["text"]
    assert result["tables"] == [[["Lauren Chen", "lauren.chen@example.com"]]]


def test_docx_preserves_paragraph_and_table_content_together() -> None:
    def _build(document):
        document.add_paragraph("Cover letter intro")
        table = document.add_table(rows=1, cols=1)
        table.rows[0].cells[0].text = "Table body content"

    payload = _docx_bytes_from(_build)
    result = _manager().extract_content(
        "doc.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        payload,
    )
    assert "Cover letter intro" in result["text"]
    assert "Table body content" in result["text"]


def test_pdf_extraction_uses_layout_mode(monkeypatch) -> None:
    # STAT-356 follow-up: pypdf's default extraction mode can drop text from a
    # side column entirely (rather than just reordering it) on multi-column
    # resume layouts — the name/contact-info column vanished in production.
    # extraction_mode="layout" preserves each run's visual position instead.
    calls: list[dict[str, object]] = []

    class _FakePage:
        def extract_text(self, **kwargs):
            calls.append(kwargs)
            return "LAUREN CHEN"

    class _FakeReader:
        def __init__(self, _stream) -> None:
            self.pages = [_FakePage()]

    monkeypatch.setattr("fileprocessor.providers.pdf_parser.PdfReader", _FakeReader)

    result = _manager().extract_content("resume.pdf", "application/pdf", b"%PDF-1.4 fake")
    assert result["parse_ok"] is True
    assert result["text"] == "LAUREN CHEN"
    # layout_mode_strip_rotated=False so rotated text (sideways labels, stamps)
    # isn't silently dropped by pypdf's layout mode default.
    assert calls == [{"extraction_mode": "layout", "layout_mode_strip_rotated": False}]


def test_pdf_extraction_recovers_form_xobjects_when_page_layout_is_empty(monkeypatch) -> None:
    """Canva-style form XObjects can be invisible to pypdf's layout mode."""
    calls: list[dict[str, object]] = []

    class _FakePage:
        def extract_text(self, **kwargs):
            calls.append(kwargs)
            if not kwargs:
                raise AssertionError("default extraction should not replace recovered form text")
            return ""

    class _FakeReader:
        def __init__(self, _stream) -> None:
            self.pages = [_FakePage()]

    monkeypatch.setattr("fileprocessor.providers.pdf_parser.PdfReader", _FakeReader)
    monkeypatch.setattr(
        "fileprocessor.providers.pdf_parser.PdfParserAdapter._extract_form_xobject_text",
        lambda _page: "TANIA JANA\ntaniajana.hh@gmail.com",
    )

    result = _manager().extract_content("canva-resume.pdf", "application/pdf", b"%PDF-1.4 fake")

    assert result["parse_ok"] is True
    assert result["text"] == "TANIA JANA\ntaniajana.hh@gmail.com"
    assert calls == [{"extraction_mode": "layout", "layout_mode_strip_rotated": False}]


def test_pdf_extraction_uses_default_when_layout_and_form_text_are_empty(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class _FakePage:
        def extract_text(self, **kwargs):
            calls.append(kwargs)
            return "" if kwargs else "Default extraction text"

    class _FakeReader:
        def __init__(self, _stream) -> None:
            self.pages = [_FakePage()]

    monkeypatch.setattr("fileprocessor.providers.pdf_parser.PdfReader", _FakeReader)
    monkeypatch.setattr(
        "fileprocessor.providers.pdf_parser.PdfParserAdapter._extract_form_xobject_text",
        lambda _page: "",
    )

    result = _manager().extract_content("fallback.pdf", "application/pdf", b"%PDF-1.4 fake")

    assert result["parse_ok"] is True
    assert result["text"] == "Default extraction text"
    assert calls == [
        {"extraction_mode": "layout", "layout_mode_strip_rotated": False},
        {},
    ]
