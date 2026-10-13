"""Legal compliance module (M6, scenario 1.5, issues #53-#61).

Deterministic rules catalog for marketplace card text and seller
documents plus an LLM-assisted risk pass; business-wide scans combine
multi-SKU cards, free text and uploaded documents into one report.
"""

from src.modules.legal import errors, schemas
from src.modules.legal.errors import LegalDocumentError, LegalScanError
from src.modules.legal.schemas import (
    BusinessScanReport,
    CardScanReport,
    DocumentReport,
    Finding,
    Rule,
    RuleCategory,
    Severity,
    SkippedItem,
)
from src.modules.legal.service import LegalService, get_legal_service

__all__ = [
    "BusinessScanReport",
    "CardScanReport",
    "DocumentReport",
    "Finding",
    "LegalDocumentError",
    "LegalScanError",
    "LegalService",
    "Rule",
    "RuleCategory",
    "Severity",
    "SkippedItem",
    "errors",
    "get_legal_service",
    "schemas",
]
