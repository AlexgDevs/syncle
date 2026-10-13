"""Legal compliance service (issues #53-#59, scenario 1.5).

Deterministic first, LLM second: the catalog engine (#53/#54/#55) finds
known violation patterns; the LLM pass (#57) catches what rules cannot
express, constrained to the catalog categories; documents (#56) are
parsed, split into sections and flow through both layers; the business
scan (#59) orchestrates multi-SKU cards plus documents into one report
with per-item partial failures recorded as skipped.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from functools import lru_cache

from pydantic import ValidationError

from src.core.documents import (
    DocumentParseError,
    DocumentParser,
    UnsupportedDocumentError,
    get_document_parser,
)
from src.core.llm import LLMError, LLMProvider, get_llm_provider
from src.core.llm.json_output import extract_json_object
from src.core.settings import get_settings
from src.modules.analytics.errors import (
    CardNotFoundError,
    CardParseError,
    OzonBrowserError,
    UnsupportedMarketplaceError,
)
from src.modules.analytics.schemas import CompetitorCard
from src.modules.legal.catalog import catalog_rules
from src.modules.legal.engine import evaluate_text
from src.modules.legal.errors import LegalDocumentError, LegalScanError
from src.modules.legal.fetch import fetch_card as default_card_fetch
from src.modules.legal.ingestion import DocumentSections, ingest_document
from src.modules.legal.prompts import (
    RISK_MAX_TOKENS,
    RISK_REVIEW_SYSTEM,
    RISK_TEMPERATURE,
    build_risk_repair_prompt,
    build_risk_review_prompt,
)
from src.modules.legal.schemas import (
    SEVERITY_ORDER,
    BusinessScanReport,
    CardScanReport,
    DocumentReport,
    Finding,
    RiskOutput,
    Severity,
    SkipErrorCode,
    SkippedItem,
)

logger = logging.getLogger(__name__)

SCAN_PROGRESS_STEP = "scanning_cards"
DOCUMENT_PROGRESS_STEP = "scanning_documents"
LLM_PROGRESS_STEP = "llm_review"

_REPAIR_ATTEMPTS = 1

CardFetch = Callable[[str], Awaitable[CompetitorCard]]


def _card_error_code(exc: Exception) -> SkipErrorCode:
    if isinstance(exc, CardNotFoundError):
        return SkipErrorCode.CARD_NOT_FOUND
    if isinstance(exc, OzonBrowserError):
        return SkipErrorCode.OZON_UNAVAILABLE
    if isinstance(exc, UnsupportedMarketplaceError):
        return SkipErrorCode.UNSUPPORTED_MARKETPLACE
    return SkipErrorCode.PARSE_FAILED


def _document_error_code(exc: Exception) -> SkipErrorCode:
    cause = exc.__cause__ if exc.__cause__ is not None else exc
    if isinstance(cause, UnsupportedDocumentError):
        return SkipErrorCode.UNSUPPORTED_DOCUMENT
    return SkipErrorCode.DOCUMENT_PARSE_FAILED


def _validation_errors(exc: ValidationError) -> list[str]:
    errors = []
    for error in exc.errors():
        loc = ".".join(str(part) for part in error["loc"]) or "root"
        errors.append(f"{loc}: {error['msg']}")
    return errors or ["invalid output"]


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings, key=lambda item: (SEVERITY_ORDER[item.severity], item.rule_id)
    )


def _dedupe_sources(sources: Sequence[str], cap: int) -> list[str]:
    seen: list[str] = []
    for value in sources:
        item = value.strip()
        if item and item not in seen:
            seen.append(item)
    return seen[:cap]


class LegalService:
    """Entry point for card/document/business compliance scans (#53-#59)."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        parser: DocumentParser | None = None,
        card_fetch: CardFetch | None = None,
    ) -> None:
        self._llm = llm
        self._parser = parser if parser is not None else get_document_parser()
        self._card_fetch = card_fetch if card_fetch is not None else default_card_fetch

    # --- deterministic layer (#53-#55) ---

    def scan_text(
        self, text: str, *, field: str = "", context: str = "card"
    ) -> list[Finding]:
        """Rule findings for one text blob; empty text -> []."""
        return evaluate_text(text, catalog_rules(context), field=field, context=context)

    def scan_card(
        self, title: str, description: str, *, source: str = ""
    ) -> CardScanReport:
        """Deterministic scan of a card title + description (#55)."""
        rules = catalog_rules("card")
        findings = evaluate_text(title, rules, field="title") + evaluate_text(
            description, rules, field="description"
        )
        return CardScanReport(source=source, findings=_sorted(findings))

    # --- LLM layer (#57) ---

    async def review_text(self, text: str, *, context: str = "card") -> list[Finding]:
        """LLM-assisted risk pass; degrades to [] without a working LLM."""
        if not text.strip():
            return []
        llm = self._llm
        if llm is None:
            logger.warning("risk review skipped: no LLM provider")
            return []
        prompt = build_risk_review_prompt(text, context=context)
        try:
            raw = await llm.complete(
                prompt,
                system=RISK_REVIEW_SYSTEM,
                temperature=RISK_TEMPERATURE,
                max_tokens=RISK_MAX_TOKENS,
            )
            output, errors = self._parse_risks(raw)
            for _ in range(_REPAIR_ATTEMPTS):
                if output is not None:
                    break
                logger.warning(
                    "risk output invalid, repairing: %s", "; ".join(errors[:3])
                )
                raw = await llm.complete(
                    build_risk_repair_prompt(text, errors, context=context),
                    system=RISK_REVIEW_SYSTEM,
                    temperature=RISK_TEMPERATURE,
                    max_tokens=RISK_MAX_TOKENS,
                )
                output, errors = self._parse_risks(raw)
        except LLMError as exc:
            logger.warning("risk review degraded: %s", exc)
            return []
        if output is None:
            logger.warning("risk review degraded: %s", "; ".join(errors[:3]))
            return []
        return _sorted([item.to_finding() for item in output.findings])

    def _parse_risks(self, raw: str) -> tuple[RiskOutput | None, list[str]]:
        data = extract_json_object(raw)
        if data is None:
            return None, ["response is not a JSON object"]
        try:
            output = RiskOutput.model_validate(data)
        except ValidationError as exc:
            return None, _validation_errors(exc)
        return output, []

    # --- documents (#56-#58) ---

    def ingest_document(self, filename: str, data: bytes) -> DocumentSections:
        """Parse one upload into text + sections (#56)."""
        return ingest_document(filename, data, parser=self._parser)

    async def scan_document(
        self,
        filename: str,
        data: bytes,
        *,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> DocumentReport:
        """Rule scan + LLM review of one document, merged (#56-#58)."""
        if on_progress is not None:
            await on_progress(DOCUMENT_PROGRESS_STEP)
        sections = self.ingest_document(filename, data)
        findings = self.scan_text(sections.text, field="document", context="document")
        if on_progress is not None:
            await on_progress(LLM_PROGRESS_STEP)
        findings += await self.review_text(sections.text, context="document")
        return DocumentReport(
            filename=filename,
            sections=len(sections.sections),
            findings=_sorted(findings),
        )

    # --- business-wide scan (#59) ---

    async def scan_business(
        self,
        sources: Sequence[str] = (),
        free_text: str = "",
        documents: Sequence[tuple[str, bytes]] = (),
        *,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> BusinessScanReport:
        """Multi-SKU cards + free text + documents into one report (#59).

        One unreadable SKU/document never aborts the scan: it lands in
        ``skipped`` with the failure reason.
        """
        cfg = get_settings()
        report = BusinessScanReport()
        if on_progress is not None:
            await on_progress(SCAN_PROGRESS_STEP)
        for source in _dedupe_sources(sources, cfg.LEGAL_CARD_CAP):
            card_report = await self._scan_one_card(source, on_progress)
            if isinstance(card_report, SkippedItem):
                report.skipped.append(card_report)
            else:
                report.cards.append(card_report)
        if free_text.strip():
            findings = self.scan_text(free_text, field="text")
            if on_progress is not None:
                await on_progress(LLM_PROGRESS_STEP)
            findings += await self.review_text(free_text)
            report.cards.append(
                CardScanReport(source="free_text", findings=_sorted(findings))
            )
        for filename, data in list(documents)[: cfg.LEGAL_DOCUMENT_CAP]:
            try:
                report.documents.append(
                    await self.scan_document(filename, data, on_progress=on_progress)
                )
            except LegalDocumentError as exc:
                logger.warning("document %r skipped: %s", filename, exc)
                report.skipped.append(
                    SkippedItem(
                        source=filename,
                        error_code=_document_error_code(exc),
                        reason=str(exc),
                    )
                )
        report.counts = self._counts(report)
        return report

    async def _scan_one_card(
        self,
        source: str,
        on_progress: Callable[[str], Awaitable[None]] | None,
    ) -> CardScanReport | SkippedItem:
        """Fetch + scan one SKU; fetch failures become SkippedItem (#59)."""
        try:
            card = await self._card_fetch(source)
        except (
            LegalScanError,
            CardNotFoundError,
            CardParseError,
            OzonBrowserError,
            UnsupportedMarketplaceError,
        ) as exc:
            logger.warning("card %r skipped: %s", source, exc)
            return SkippedItem(
                source=source,
                error_code=_card_error_code(exc),
                reason=str(exc),
            )
        report = self.scan_card(card.title or "", card.description or "", source=source)
        if on_progress is not None:
            await on_progress(LLM_PROGRESS_STEP)
        report.findings = _sorted(
            report.findings
            + await self.review_text(f"{card.title}\n{card.description}")
        )
        return report

    @staticmethod
    def _counts(report: BusinessScanReport) -> dict[str, int]:
        counts = {severity.value: 0 for severity in Severity}
        for item in report.cards:
            for finding in item.findings:
                counts[finding.severity.value] += 1
        for document in report.documents:
            for finding in document.findings:
                counts[finding.severity.value] += 1
        return counts


@lru_cache
def get_legal_service() -> LegalService:
    """Process-wide singleton: shares the LLM provider and parsers."""
    return LegalService(
        llm=get_llm_provider(),
        parser=get_document_parser(),
        card_fetch=default_card_fetch,
    )
