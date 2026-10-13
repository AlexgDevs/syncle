"""Deterministic rules evaluation core (issue #53).

``evaluate_text`` runs a rule catalog against plain text and returns
findings with the matched excerpt — no LLM involved. Normalization is
length-preserving (lowercase, ё/е, quote folding), so match spans from
the normalized copy index straight into the original text for excerpts.
Empty or odd input yields an empty list; never raises on text content.
"""

import re
from collections.abc import Iterable
from functools import lru_cache

from src.modules.legal.schemas import Finding, Rule, SEVERITY_ORDER, Severity

MAX_SCAN_LEN = 50_000
_EXCERPT_RADIUS = 60

# Length-preserving folds: normalized spans stay valid for the original
_NORMALIZE_TABLE = str.maketrans(
    {
        "ё": "е",
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "\u00a0": " ",
    }
)


def _normalize(text: str) -> str:
    return text.lower().translate(_NORMALIZE_TABLE)


@lru_cache
def _keyword_regex(keyword: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(keyword) + r"(?!\w)")


@lru_cache
def _pattern_regex(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _excerpt(original: str, start: int, end: int) -> str:
    left = max(0, start - _EXCERPT_RADIUS)
    right = min(len(original), end + _EXCERPT_RADIUS)
    fragment = " ".join(original[left:right].split())
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(original) else ""
    return f"{prefix}{fragment}{suffix}"[: 2 * _EXCERPT_RADIUS + 40]


def _match(rule: Rule, normalized: str) -> tuple[int, int] | None:
    """First matching span in the normalized text, or None."""
    for keyword in rule.keywords:
        found = _keyword_regex(_normalize(keyword)).search(normalized)
        if found:
            return found.start(), found.end()
    for pattern in rule.patterns:
        found = _pattern_regex(pattern).search(normalized)
        if found:
            return found.start(), found.end()
    return None


def evaluate_text(
    text: str,
    rules: Iterable[Rule],
    *,
    field: str = "",
    context: str = "card",
) -> list[Finding]:
    """Evaluate every applicable rule against ``text`` (#53).

    One finding per rule (the first hit); findings come back sorted by
    severity. ``context`` filters rules by their ``contexts`` set.
    """
    if not text or not text.strip():
        return []
    clipped = text[:MAX_SCAN_LEN]
    normalized = _normalize(clipped)
    findings: list[Finding] = []
    for rule in rules:
        if context not in rule.contexts:
            continue
        span = _match(rule, normalized)
        if span is None:
            continue
        start, end = span
        findings.append(
            Finding(
                rule_id=rule.id,
                category=rule.category,
                severity=rule.severity,
                excerpt=_excerpt(clipped, start, end),
                description=rule.description,
                source=rule.source,
                field=field,
            )
        )
    findings.sort(key=lambda item: (SEVERITY_ORDER[item.severity], item.rule_id))
    return findings


def group_by_severity(findings: Iterable[Finding]) -> dict[Severity, list[Finding]]:
    """Bucket findings for reporting, critical first."""
    grouped: dict[Severity, list[Finding]] = {severity: [] for severity in Severity}
    for finding in findings:
        grouped[finding.severity].append(finding)
    return grouped
