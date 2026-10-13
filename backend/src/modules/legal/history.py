"""Scan history persistence (issue #61).

One-shot writes from the job path open their own null-pool session
(the job has no injected session). Failures only log: a history miss
never breaks scan delivery.

History is keyed by the domain ``user_id`` (FK -> users); ``chat_id``
is an optional adapter hint. Retention and cleanup (#61 AC):
- scans are kept for ``LEGAL_SCAN_RETENTION_DAYS`` (90 days);
- documents cascade from their scan row (ON DELETE CASCADE);
- cleanup statement (wire to a scheduler when one lands):

    DELETE FROM legal_scans
    WHERE created_at < NOW() - INTERVAL '90 days';
"""

import logging
from uuid import UUID

from src.core.database.session import get_null_pool_session_factory
from src.modules.legal.models import LegalDocument, LegalScan
from src.modules.legal.repository import (
    LegalDocumentRepository,
    LegalScanRepository,
)
from src.modules.legal.schemas import (
    BusinessScanReport,
    CardScanReport,
    Severity,
)

logger = logging.getLogger(__name__)

LEGAL_SCAN_RETENTION_DAYS = 90

_SCOPE_CARD = "card"
_SCOPE_BUSINESS = "business"

ScanReport = BusinessScanReport | CardScanReport


def _counts(report: ScanReport) -> dict[str, int]:
    counts = {severity.value: 0 for severity in Severity}
    if isinstance(report, BusinessScanReport):
        for card in report.cards:
            for finding in card.findings:
                counts[finding.severity.value] += 1
        for document in report.documents:
            for finding in document.findings:
                counts[finding.severity.value] += 1
    else:
        for finding in report.findings:
            counts[finding.severity.value] += 1
    return counts


async def save_scan(
    user_id: UUID,
    report: ScanReport,
    *,
    chat_id: int | None = None,
    scope: str = _SCOPE_BUSINESS,
) -> None:
    """Persist one scan report plus document metadata; best effort."""
    try:
        factory = get_null_pool_session_factory()
        async with factory() as session:
            scan = await LegalScanRepository(session).add(
                {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "scope": scope,
                    "counts": _counts(report),
                    "result": report.model_dump(mode="json"),
                }
            )
            documents = LegalDocumentRepository(session)
            stored = report.documents if isinstance(report, BusinessScanReport) else []
            for document in stored:
                await documents.add(
                    {
                        "scan_id": scan.id,
                        "filename": document.filename[:255],
                        "sections": document.sections,
                    }
                )
            await session.commit()
    except Exception:  # noqa: BLE001 — history is best effort
        logger.warning("legal scan history write failed", exc_info=True)


async def load_recent_scans(user_id: UUID, limit: int = 10) -> list[LegalScan]:
    """Newest scans for one user; newest first."""
    factory = get_null_pool_session_factory()
    async with factory() as session:
        rows = await LegalScanRepository(session).get_filtered(
            limit=limit, offset=0, order_by=LegalScan.created_at.desc(), user_id=user_id
        )
        return list(rows)


__all__ = [
    "LegalDocument",
    "LegalScan",
    "LEGAL_SCAN_RETENTION_DAYS",
    "load_recent_scans",
    "save_scan",
]
