"""Document ingestion: upload bytes -> text -> sections (issue #56).

Wraps the core DocumentParser (#15) and splits the extracted text into
LLM-sized sections: blank-line paragraphs are merged into chunks up to
``MAX_SECTION_LEN``; the section count is capped to bound LLM cost.
"""

import re

from pydantic import BaseModel, ConfigDict, Field

from src.core.documents import DocumentParseError, DocumentParser, get_document_parser
from src.modules.legal.errors import LegalDocumentError

MAX_SECTION_LEN = 1_500
MAX_SECTIONS = 24

_SPLIT = re.compile(r"\n\s*\n")


class DocumentSections(BaseModel):
    """Ingested document ready for rule scan and LLM review (#56/#58)."""

    model_config = ConfigDict(extra="ignore")

    filename: str
    text: str
    sections: list[str] = Field(default_factory=list)


def split_sections(text: str) -> list[str]:
    """Split extracted text into LLM-sized sections; empty text -> []."""
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    buffer = ""
    for paragraph in _SPLIT.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        while len(paragraph) > MAX_SECTION_LEN:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.append(paragraph[:MAX_SECTION_LEN])
            paragraph = paragraph[MAX_SECTION_LEN:].strip()
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= MAX_SECTION_LEN:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph
    if buffer:
        chunks.append(buffer)
    return chunks[:MAX_SECTIONS]


def ingest_document(
    filename: str,
    data: bytes,
    *,
    parser: DocumentParser | None = None,
) -> DocumentSections:
    """Parse one upload and split it into sections (#56).

    Raises:
        LegalDocumentError: unsupported format or broken file.
    """
    active = parser if parser is not None else get_document_parser()
    try:
        parsed = active.parse(data, filename=filename)
    except DocumentParseError as exc:
        raise LegalDocumentError(
            f"document {filename!r} could not be parsed: {exc}"
        ) from exc
    return DocumentSections(
        filename=filename,
        text=parsed.text,
        sections=split_sections(parsed.text),
    )
