"""Settlement report ingestion and column mapping (issues #49, #50).

Contract (#49): raw bytes plus the original filename → mapped
``SettlementRow`` list. Delegates extraction to the shared
``DocumentParser`` (#15) and wraps its failures into ``ReportParseError``
so the bot edge can answer with RU messages. Type and size validation
lives at the bot edge (the file is checked before download); this
module re-checks the extension defensively.

Mapping (#50): the header row is located by known column synonyms
(RU/EN, lowercased substring match); recognized columns map to the
``SettlementRow`` fields, everything numeric stays in ``unknown`` for
the detector (#51).
"""

from decimal import Decimal, InvalidOperation

from src.core.documents.errors import DocumentParseError, UnsupportedDocumentError
from src.core.documents.parser import ParsedDocument, get_document_parser
from src.modules.finance.errors import ReportParseError
from src.modules.finance.schemas import SettlementRow

SUPPORTED_SUFFIXES = (".xlsx", ".csv", ".pdf")

# Header synonyms per target field. Order matters inside a header scan:
# specific fields (returns) must win over generic ones (sales).
_COLUMN_SYNONYMS: dict[str, tuple[str, ...]] = {
    "period": ("период", "дата", "date", "period", "неделя", "за период"),
    "returns": ("возврат", "return"),
    "commissions": ("комисси", "вознагражд", "commission"),
    "logistics": ("логист", "доставк", "перевоз", "транспорт"),
    "storage": ("хранен", "storage"),
    "fines": ("штраф", "penalt", "fine"),
    "adjustments": ("корректи", "перерасчет", "перерасчёт", "адресн", "adjust"),
    "sales": (
        "продаж",
        "выручк",
        "sales",
        "revenue",
        "оборот",
        "цена реализации",
        "к перечислению",
        "перечислен",
    ),
}

# Quantity markers: "Кол-во продаж" is a count, never a sales amount
_QUANTITY_MARKERS = ("кол-во", "количество", "шт", "индекс")

_FIELDS = (
    "period",
    "returns",
    "commissions",
    "logistics",
    "storage",
    "fines",
    "adjustments",
    "sales",
)

_MIN_MATCHES = 2  # a header row must recognize at least two columns
_MAX_ROWS = 5_000  # matches DocumentParser.MAX_ROWS


def parse_money(cell: str) -> Decimal | None:
    """Parse a RU/EN money cell: ``"1 234,56"`` / ``"-12,5"`` / ``"7.3"``.

    Spaces (incl. NBSP), currency signs and percent are stripped;
    ``None`` when the cell is not a number.
    """
    text = (
        cell.replace("\xa0", " ")
        .replace("₽", "")
        .replace("%", "")
        .replace(" ", "")
        .strip()
    )
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    if "," in text and "." in text:
        # "1,234.56" style: the last separator is the decimal point
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    return -value if negative else value


def _normalize_header(cell: str) -> str:
    return cell.lower().replace("_", " ").strip()


def _match_field(header: str) -> str | None:
    normalized = _normalize_header(header)
    for field in _FIELDS:
        if field == "sales" and any(m in normalized for m in _QUANTITY_MARKERS):
            continue
        if any(synonym in normalized for synonym in _COLUMN_SYNONYMS[field]):
            return field
    return None


def _find_header(rows: list[list[str]]) -> tuple[int, dict[int, str]] | None:
    """Locate the header row and its column → field mapping (#50).

    Scans the whole table: multi-sheet seller exports put a summary block
    first, so a fixed 10-row window misses the real detail header. The
    candidate with the most matched fields wins (first on ties).
    """
    best: tuple[int, dict[int, str]] | None = None
    best_score = 0
    for index, row in enumerate(rows):
        mapping: dict[int, str] = {}
        for column, cell in enumerate(row):
            field = _match_field(cell)
            if field is not None and field not in mapping.values():
                mapping[column] = field
        if len(mapping) >= _MIN_MATCHES and len(mapping) > best_score:
            best = (index, mapping)
            best_score = len(mapping)
            if best_score == len(_FIELDS):
                break
    return best


def _cell(row: list[str], column: int) -> str:
    if column >= len(row):
        return ""
    return row[column]


def _is_section_title(row: list[str]) -> bool:
    """Single non-empty cell holding text — a sheet/section banner.

    Multi-sheet exports are flattened into one stream; a banner after the
    data rows marks the end of the mapped table (the next sheet starts).
    """
    non_empty = [cell.strip() for cell in row if cell.strip()]
    if len(non_empty) != 1:
        return False
    return parse_money(non_empty[0]) is None


def map_rows(rows: list[list[str]]) -> list[SettlementRow]:
    """Map raw table rows onto ``SettlementRow`` items (#50).

    Picks the best matching header across the whole document and stops
    the table at the next section banner; returns [] when there is
    nothing to map.
    """
    if not rows:
        return []
    located = _find_header(rows)
    if located is None:
        return []
    header_index, mapping = located
    # Field → first column carrying it (unknown headers kept separately)
    columns: dict[str, int] = {field: column for column, field in mapping.items()}
    unknown_names = {
        column: rows[header_index][column].strip()
        for column in range(len(rows[header_index]))
        if column not in mapping
    }
    mapped: list[SettlementRow] = []
    for index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if len(mapped) >= _MAX_ROWS:
            break
        if mapped and _is_section_title(row):
            break
        values: dict[str, Decimal] = {}
        for field in _FIELDS:
            column = columns.get(field)
            if column is None:
                continue
            parsed = parse_money(_cell(row, column))
            if parsed is not None:
                values[field] = parsed
        unknown: dict[str, Decimal] = {}
        for column, name in unknown_names.items():
            parsed = parse_money(_cell(row, column))
            if parsed is not None and name:
                unknown[name] = parsed
        # Skip rows without any number (totals/notes/empty lines)
        if not values and not unknown:
            continue
        sales = values.get("sales", Decimal("0"))
        mapped.append(
            SettlementRow(
                row_number=index,  # 1-based row number in the source table
                period=_cell(row, columns["period"]) if "period" in columns else "",
                sales=sales,
                returns=abs(values.get("returns", Decimal("0"))),
                commissions=abs(values.get("commissions", Decimal("0"))),
                logistics=abs(values.get("logistics", Decimal("0"))),
                storage=abs(values.get("storage", Decimal("0"))),
                fines=abs(values.get("fines", Decimal("0"))),
                adjustments=values.get("adjustments", Decimal("0")),
                unknown=unknown,
            )
        )
    return mapped


def extract_document(data: bytes, *, filename: str) -> ParsedDocument:
    """Run the shared DocumentParser, wrapping failures (#49)."""
    try:
        return get_document_parser().parse(data, filename=filename)
    except UnsupportedDocumentError as exc:
        raise ReportParseError(str(exc)) from exc
    except DocumentParseError as exc:
        raise ReportParseError(str(exc)) from exc


def parse_settlement_report(data: bytes, *, filename: str) -> list[SettlementRow]:
    """Full #49/#50 contract: bytes + filename → mapped rows.

    Raises ``ReportParseError`` for unsupported types, broken files,
    missing tabular data or headers the mapper does not recognize.
    """
    lowered = filename.lower()
    if not any(lowered.endswith(suffix) for suffix in SUPPORTED_SUFFIXES):
        raise ReportParseError(f"unsupported report format: {filename!r}")
    document = extract_document(data, filename=filename)
    rows = map_rows(document.rows)
    if not rows:
        raise ReportParseError("no tabular data with recognizable columns")
    return rows
