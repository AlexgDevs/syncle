"""Prompt evaluation harness for the weaknesses prompt (issue #13).

Golden cases are static card snapshots; the offline runner (default)
validates checked-in baseline outputs against structure and keyword
checks without any network access. `--live` additionally re-runs the
configured LLM provider and checks its output the same way.

Usage (from backend/):

    uv run python -m src.modules.analytics.golden            # offline
    uv run python -m src.modules.analytics.golden --live     # + provider run
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.modules.analytics.schemas import CompetitorCard
from src.modules.analytics.weakness import parse_weaknesses

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "golden"

_MIN_ITEM_LENGTH = 20


@dataclass
class GoldenExpect:
    min_items: int = 1
    max_items: int = 5
    required_keywords: list[str] = field(default_factory=list)
    forbidden_keywords: list[str] = field(default_factory=list)


@dataclass
class GoldenCase:
    id: str
    own: CompetitorCard
    rival: CompetitorCard
    missed_keys: list[str]
    expect: GoldenExpect
    baseline: str


def load_cases(data_dir: Path = DEFAULT_DATA_DIR) -> list[GoldenCase]:
    raw = json.loads((data_dir / "cases.json").read_text(encoding="utf-8"))
    cases: list[GoldenCase] = []
    for entry in raw:
        expect_raw = entry.get("expect") or {}
        cases.append(
            GoldenCase(
                id=entry["id"],
                own=CompetitorCard.model_validate(entry["own"]),
                rival=CompetitorCard.model_validate(entry["rival"]),
                missed_keys=list(entry.get("missed_keys") or []),
                expect=GoldenExpect(
                    min_items=int(expect_raw.get("min_items", 1)),
                    max_items=int(expect_raw.get("max_items", 5)),
                    required_keywords=list(expect_raw.get("required_keywords") or []),
                    forbidden_keywords=list(expect_raw.get("forbidden_keywords") or []),
                ),
                baseline=entry["baseline"],
            )
        )
    return cases


def check_output(case: GoldenCase, raw: str) -> list[str]:
    """Structure + keyword checks; returns violations (empty = pass)."""
    violations: list[str] = []
    items = parse_weaknesses(raw)
    if not items:
        return ["output did not parse into content_weaknesses"]
    if len(items) < case.expect.min_items:
        violations.append(f"too few items: {len(items)} < {case.expect.min_items}")
    if len(items) > case.expect.max_items:
        violations.append(f"too many items: {len(items)} > {case.expect.max_items}")
    short = [i for i, item in enumerate(items) if len(item) < _MIN_ITEM_LENGTH]
    if short:
        violations.append(f"items too short: indexes {short}")
    if len(set(items)) != len(items):
        violations.append("duplicate items")
    blob = " ".join(items).lower()
    for keyword in case.expect.required_keywords:
        if keyword.lower() not in blob:
            violations.append(f"missing required keyword: {keyword!r}")
    for keyword in case.expect.forbidden_keywords:
        if keyword.lower() in blob:
            violations.append(f"forbidden keyword present: {keyword!r}")
    return violations


def run_offline(cases: list[GoldenCase], data_dir: Path) -> int:
    failures = 0
    for case in cases:
        baseline_path = data_dir / case.baseline
        if not baseline_path.exists():
            print(f"[FAIL] {case.id}: baseline missing ({case.baseline})")
            failures += 1
            continue
        raw = baseline_path.read_text(encoding="utf-8")
        violations = check_output(case, raw)
        if violations:
            failures += 1
            print(f"[FAIL] {case.id}")
            for violation in violations:
                print(f"       - {violation}")
        else:
            print(f"[OK ] {case.id}")
    return failures


async def run_live(cases: list[GoldenCase]) -> int:
    from src.core.llm import get_llm_provider
    from src.modules.analytics.prompts import (
        COMPARISON_MAX_TOKENS,
        COMPARISON_SYSTEM,
        COMPARISON_TEMPERATURE,
        build_comparison_prompt,
    )

    provider = get_llm_provider()
    if provider is None:
        print("[FAIL] --live: LLM provider is not configured")
        return 1
    failures = 0
    for case in cases:
        prompt = build_comparison_prompt(case.own, case.rival, case.missed_keys)
        raw = await provider.complete(
            prompt,
            system=COMPARISON_SYSTEM,
            temperature=COMPARISON_TEMPERATURE,
            max_tokens=COMPARISON_MAX_TOKENS,
        )
        violations = check_output(case, raw)
        if violations:
            failures += 1
            print(f"[FAIL] {case.id} (live)")
            for violation in violations:
                print(f"       - {violation}")
        else:
            print(f"[OK ] {case.id} (live)")
    return failures


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden-set prompt evaluation")
    parser.add_argument(
        "--live",
        action="store_true",
        help="also run the configured LLM provider (needs network/key)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="golden dataset directory",
    )
    args = parser.parse_args(argv)

    cases = load_cases(args.data_dir)
    if not cases:
        print("[FAIL] no golden cases found")
        return 1
    failures = run_offline(cases, args.data_dir)
    if args.live:
        failures += await run_live(cases)
    total = len(cases) * (2 if args.live else 1)
    print(f"golden set: {total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
