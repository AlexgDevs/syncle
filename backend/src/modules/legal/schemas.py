"""Schemas for the legal compliance module (issues #53-#59, scenario 1.5).

``Finding`` is the shared L03 report unit: rule findings carry the
catalog rule id and a source reference, LLM-assisted findings (#57)
carry only a category (no free-form law citations outside the catalog).
"""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


class RuleCategory(str, Enum):
    PACKAGING_MARKING = "packaging_marking"
    PROHIBITED_CLAIMS = "prohibited_claims"
    MANDATORY_DISCLOSURE = "mandatory_disclosure"


# Where a rule may fire: "card" = marketplace card text, "document" = seller docs
ScanContext = str  # "card" | "document"


class Rule(BaseModel):
    """One catalog entry (#53/#54): data, no behavior."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: str
    category: RuleCategory
    severity: Severity
    description: str  # RU: what the rule prohibits/requires
    source: str  # RU: legal source reference (ТР ТС, 2300-ФЗ, КоАП, ...)
    example: str  # RU: example violation wording
    keywords: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)  # regex, IGNORECASE
    contexts: frozenset[str] = frozenset({"card", "document"})


class Finding(BaseModel):
    """L03 finding: shared by card scan (#55), documents (#58) and LLM (#57)."""

    model_config = ConfigDict(extra="ignore")

    rule_id: str = ""  # catalog id; empty for LLM-assisted findings
    category: RuleCategory
    severity: Severity
    excerpt: str  # quoted fragment from the scanned text
    description: str  # RU: what is wrong
    source: str = ""  # RU reference; empty for LLM-assisted findings
    field: str = ""  # "title" | "description" | "document" | ""


class CardScanReport(BaseModel):
    """Deterministic scan of one card title + description (#55)."""

    model_config = ConfigDict(extra="ignore")

    source: str = ""
    findings: list[Finding] = Field(default_factory=list)


_RISK_EXCERPT_LIMIT = 200
_RISK_DESCRIPTION_LIMIT = 300


class RiskItem(BaseModel):
    """One LLM-assisted finding before conversion to the shared Finding (#57)."""

    model_config = ConfigDict(extra="ignore")

    category: RuleCategory
    severity: Severity
    excerpt: str = ""
    description: str = ""

    def to_finding(self) -> Finding:
        return Finding(
            category=self.category,
            severity=self.severity,
            excerpt=self.excerpt.strip()[:_RISK_EXCERPT_LIMIT],
            description=self.description.strip()[:_RISK_DESCRIPTION_LIMIT],
        )


class RiskOutput(BaseModel):
    """LLM risk-review response envelope (issue #57)."""

    model_config = ConfigDict(extra="ignore")

    findings: list[RiskItem] = Field(default_factory=list)


class DocumentReport(BaseModel):
    """Findings for one uploaded document (#56-#58)."""

    model_config = ConfigDict(extra="ignore")

    filename: str
    sections: int = 0
    findings: list[Finding] = Field(default_factory=list)


class SkipErrorCode(str, Enum):
    """Machine codes for skipped scan items (#59); the bot maps them to RU text."""

    CARD_NOT_FOUND = "card_not_found"
    OZON_UNAVAILABLE = "ozon_unavailable"
    UNSUPPORTED_MARKETPLACE = "unsupported_marketplace"
    PARSE_FAILED = "parse_failed"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    DOCUMENT_PARSE_FAILED = "document_parse_failed"


class SkippedItem(BaseModel):
    """A business-scan item that could not be processed (#59).

    ``reason`` is EN technical diagnostics kept in the stored report;
    users see the RU text mapped from ``error_code``.
    """

    model_config = ConfigDict(extra="ignore")

    source: str
    error_code: SkipErrorCode
    reason: str = ""


class BusinessScanReport(BaseModel):
    """Combined multi-SKU + documents report (#59)."""

    model_config = ConfigDict(extra="ignore")

    cards: list[CardScanReport] = Field(default_factory=list)
    documents: list[DocumentReport] = Field(default_factory=list)
    skipped: list[SkippedItem] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)  # severity value -> count


class LegalJobPayload(BaseModel):
    """Light taskiq payload for the business scan (#59/#60).

    Delivery metadata rides in the same dict (extra="ignore" drops it);
    documents travel through the stash, not the payload. ``user_id`` is
    the history key (adapter-independent), ``chat_id``/``status_message_id``
    are adapter concerns used only for delivery.
    """

    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    chat_id: int
    status_message_id: int
    sources: list[str] = Field(default_factory=list)
    free_text: str = ""


class LegalCardPayload(BaseModel):
    """Light taskiq payload for the quick card scan (#60).

    Deterministic rules only — no LLM in this path.
    """

    model_config = ConfigDict(extra="ignore")

    user_id: UUID
    chat_id: int
    status_message_id: int
    source: str
