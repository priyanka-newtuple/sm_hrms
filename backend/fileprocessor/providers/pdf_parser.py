"""PDF adapter for converting pdf bytes to text for LLM."""

from __future__ import annotations

from io import BytesIO

from pypdf import PageObject, PdfReader
from pypdf.generic import DictionaryObject, NameObject


class PdfParserAdapter:
    """Adapter for PDF content."""

    def supports(self, content_type: str, filename: str) -> bool:
        return content_type == "application/pdf" or filename.lower().endswith(".pdf")

    @classmethod
    def _extract_page_text(cls, page: PageObject) -> str:
        """Prefer layout extraction, falling back for unsupported PDF structures.

        pypdf's layout mode preserves multi-column positioning, but currently
        returns an empty string for some PDFs whose text is nested in form
        XObjects (including Canva-generated resumes). Try those nested forms in
        layout mode before using default extraction, which can lose side-column
        text such as names and contact details.
        """
        layout_text = (
            page.extract_text(extraction_mode="layout", layout_mode_strip_rotated=False) or ""
        )
        if layout_text.strip():
            return layout_text

        try:
            form_text = cls._extract_form_xobject_text(page)
        except Exception:
            # Nested-form recovery is best effort. Preserve the pre-layout
            # behavior for malformed or otherwise unsupported object graphs.
            form_text = ""
        return form_text if form_text.strip() else (page.extract_text() or "")

    @staticmethod
    def _extract_form_xobject_text(page: PageObject) -> str:
        """Recursively extract layout text from form XObjects on one page."""
        parts: list[str] = []
        seen: set[tuple[int, int] | int] = set()

        def visit(resources: object) -> None:
            if not isinstance(resources, dict):
                return
            xobjects = resources.get("/XObject")
            if not isinstance(xobjects, dict):
                return

            for reference in xobjects.values():
                form = reference.get_object()
                if form.get("/Subtype") != "/Form":
                    continue
                identity: tuple[int, int] | int
                if hasattr(reference, "idnum"):
                    identity = (reference.idnum, reference.generation)
                else:
                    identity = id(form)
                if identity in seen:
                    continue
                seen.add(identity)

                bbox = form.get("/BBox")
                if bbox is not None and len(bbox) == 4:
                    width = max(float(bbox[2]) - float(bbox[0]), 1.0)
                    height = max(float(bbox[3]) - float(bbox[1]), 1.0)
                    form_page = PageObject.create_blank_page(page.pdf, width, height)
                    form_page.pop(NameObject("/Parent"), None)
                    form_page[NameObject("/Resources")] = (
                        form.get("/Resources") or DictionaryObject()
                    )
                    form_page[NameObject("/Contents")] = form
                    text = (
                        form_page.extract_text(
                            extraction_mode="layout",
                            layout_mode_strip_rotated=False,
                        )
                        or ""
                    )
                    if text.strip():
                        parts.append(text)

                visit(form.get("/Resources"))

        visit(page.get("/Resources"))
        return "\n".join(parts)

    def adapt(self, file_bytes: bytes, filename: str, content_type: str) -> dict[str, object]:
        # Let parse errors propagate so extract_content can report parse_ok=False
        # instead of silently returning empty text.
        reader = PdfReader(BytesIO(file_bytes))
        # "layout" mode preserves each text run's visual position. Default-mode
        # extraction reads pypdf's internal content-stream order, which on a
        # multi-column resume (name/contact info in a side column) can drop that
        # column's text entirely instead of just reordering it.
        # layout_mode_strip_rotated defaults to True in pypdf, which would drop
        # rotated text (sideways labels, stamps) instead of just reordering it —
        # the same silent-content-loss failure this mode switch was meant to fix.
        extracted_text = "\n".join(self._extract_page_text(page) for page in reader.pages)

        return {
            "adapter": "pdf",
            "filename": filename,
            "content_type": content_type,
            "text": extracted_text,
            "images": [],
            "tables": [],
        }
