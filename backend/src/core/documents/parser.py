"""Document text extraction port and adapter (issue #15).

Receives raw upload bytes plus the original filename and returns plain
text (and rows where the format is tabular). No aiogram imports — the
bot adapter hands over bytes at its own boundary. Used by finance N06
and legal L04/L05.

Guards: unsupported extension raises ``UnsupportedDocumentError``;
broken files raise ``DocumentParseError``; text and row counts are
capped so a hostile upload cannot exhaust memory.
"""

import csv
import io
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.core.documents.errors import DocumentParseError, UnsupportedDocumentError

MAX_TEXT_LEN = 200_000
MAX_ROWS = 5_000
MAX_ROWS_SHEET = 5_000

_SUPPORTED = {".pdf", ".docx", ".xlsx", ".csv"}

# CSV encodings seen on RU marketplace seller exports, in probe order
_CSV_ENCODINGS = ("utf-8-sig", "cp1251", "utf-16", "latin-1")


class ParsedDocument(BaseModel):
    """Extraction result: plain text plus tabular rows where applicable."""

    model_config = ConfigDict(extra="ignore")

    text: str = ""
    rows: list[list[str]] = Field(default_factory=list)
    pages: int = 0


class DocumentParser(Protocol):
    """Port for extracting text from seller document uploads (#15)."""

    def parse(self, data: bytes, *, filename: str) -> ParsedDocument:
        """Return the extracted content; raises DocumentParseError."""
        ...


def _ext(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _clamp_text(text: str) -> str:
    text = text.replace("\x00", "")
    return text[:MAX_TEXT_LEN]


def _rows_to_text(rows: list[list[str]]) -> str:
    return _clamp_text("\n".join("\t".join(cell for cell in row) for row in rows))


def _parse_pdf(data: bytes) -> ParsedDocument:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 — pypdf raises many types
        raise DocumentParseError(f"PDF parsing failed: {type(exc).__name__}.") from exc
    return ParsedDocument(text=_clamp_text("\n".join(pages)), pages=len(pages))


def _parse_docx(data: bytes) -> ParsedDocument:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 — lxml errors vary
        raise DocumentParseError(f"DOCX parsing failed: {type(exc).__name__}.") from exc
    parts: list[str] = [
        paragraph.text for paragraph in document.paragraphs if paragraph.text
    ]
    for table in document.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return ParsedDocument(text=_clamp_text("\n".join(parts)))


def _cell_text(cell: Any) -> str:
    value = cell.value
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _parse_xlsx(data: bytes) -> ParsedDocument:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — openpyxl errors vary
        raise DocumentParseError(f"XLSX parsing failed: {type(exc).__name__}.") from exc
    rows: list[list[str]] = []
    try:
        for sheet in workbook.worksheets:
            for index, row in enumerate(sheet.iter_rows(values_only=True)):
                if len(rows) >= MAX_ROWS_SHEET:
                    break
                cells = ["" if value is None else str(value) for value in row]
                if any(cell.strip() for cell in cells):
                    rows.append(cells)
    finally:
        workbook.close()
    return ParsedDocument(text=_rows_to_text(rows), rows=rows)


def _decode_csv(data: bytes) -> str:
    for encoding in _CSV_ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError("CSV encoding is not recognized.")


def _parse_csv(data: bytes) -> ParsedDocument:
    text = _decode_csv(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";" if text.count(";") > text.count(",") else ","
    try:
        rows = [
            [cell.strip() for cell in row]
            for row in csv.reader(io.StringIO(text), dialect)
        ][:MAX_ROWS]
    except csv.Error as exc:
        raise DocumentParseError(f"CSV parsing failed: {exc}.") from exc
    return ParsedDocument(text=_rows_to_text(rows), rows=rows)


class UploadDocumentParser:
    """Reference adapter: dispatches on the filename extension (#15)."""

    def parse(self, data: bytes, *, filename: str) -> ParsedDocument:
        if not data:
            raise DocumentParseError("document is empty")
        ext = _ext(filename)
        if ext not in _SUPPORTED:
            raise UnsupportedDocumentError(
                f"unsupported document format {ext or '(no extension)'!r}"
            )
        if ext == ".pdf":
            return _parse_pdf(data)
        if ext == ".docx":
            return _parse_docx(data)
        if ext == ".xlsx":
            return _parse_xlsx(data)
        return _parse_csv(data)


@lru_cache
def get_document_parser() -> DocumentParser:
    """Process-wide singleton (convention of the sibling ports)."""
    return UploadDocumentParser()
