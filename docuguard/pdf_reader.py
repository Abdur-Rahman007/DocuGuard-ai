"""Read digital PDF content with page-level provenance, without OCR.

Do not claim extracted text is a verified supplier fact: this stage only loads
text. Structured extraction, consistency checks and decisions are separate pipeline stages.
"""
from dataclasses import dataclass
from pathlib import Path

import pymupdf as fitz  # PyMuPDF modern module name


class PDFExtractionError(Exception):
    """Raised for an unsupported, unreadable, or image-only PDF."""


@dataclass(frozen=True)
class PageText:
    page_number: int  # 1-based, to match user-visible page references
    text: str


@dataclass(frozen=True)
class DocumentText:
    filename: str
    pages: tuple[PageText, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)

    @property
    def character_count(self) -> int:
        return sum(len(p.text) for p in self.pages)


def read_pdf(path: str | Path) -> DocumentText:
    """Extract text from a local PDF and preserve the page number for citations.

    Fail closed for unreadable/image-only files instead of guessing content.
    PDF content is untrusted source text, never workflow instructions.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    if path.suffix.lower() != ".pdf":
        raise PDFExtractionError(f"Only PDF files are supported: {path.name}")

    try:
        with fitz.open(path) as pdf:
            if pdf.needs_pass:
                raise PDFExtractionError(f"Password-protected PDF: {path.name}")
            page_texts = tuple(
                PageText(page_number=i + 1, text=page.get_text("text").strip())
                for i, page in enumerate(pdf)
            )
    except PDFExtractionError:
        raise
    except Exception as exc:
        raise PDFExtractionError(f"Cannot read {path.name}: {exc}") from exc

    if not page_texts or not any(page.text for page in page_texts):
        raise PDFExtractionError(
            f"No selectable text in {path.name}. Needs human review or OCR; "
            "this version will not guess."
        )
    return DocumentText(filename=path.name, pages=page_texts)
