"""Scoring logic for the known-conflicts benchmark.

Database-free on purpose: the caller (scripts/eval_conflicts.py) loads the
extracted entities and the detected inconsistencies from the database and
passes them in as plain objects.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DETECTED = "detected"
EXTRACTED_NOT_FLAGGED = "extracted_not_flagged"
PARTIALLY_EXTRACTED = "partially_extracted"
NOT_EXTRACTED = "not_extracted"

SPECIFICATION = "Specification"


@dataclass(frozen=True)
class ExtractedEntity:
    entity_type: str
    value: str
    input_type: str


@dataclass(frozen=True)
class Inconsistency:
    key: str
    values: tuple[str, ...]


@dataclass
class ConflictResult:
    conflict_id: str
    title: str
    status: str
    decision: dict[str, Any] | None = None
    matched_values: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    results: list[ConflictResult]
    unmatched_inconsistencies: list[Inconsistency]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def detected(self) -> int:
        return sum(1 for r in self.results if r.status == DETECTED)

    @property
    def recall(self) -> float:
        return self.detected / self.total if self.total else 0.0


def load_known_conflicts(path: str | Path) -> list[dict[str, Any]]:
    """Load a fixture and fail early on a malformed entry or a bad regex."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    conflicts = data["conflicts"]
    for conflict in conflicts:
        for key in ("id", "title", "sources"):
            if key not in conflict:
                raise ValueError(f"conflict is missing '{key}': {conflict}")
        if len(conflict["sources"]) < 2:
            raise ValueError(f"conflict '{conflict['id']}' needs at least two sources")
        for source in conflict["sources"]:
            if "input_type" not in source or "token_regex" not in source:
                raise ValueError(f"bad source in conflict '{conflict['id']}'")
            re.compile(source["token_regex"], re.IGNORECASE)  # raises re.error
    return conflicts


def _matching_values(
    conflict: dict[str, Any], source: dict[str, Any], entities: list[ExtractedEntity]
) -> list[str]:
    pattern = re.compile(source["token_regex"], re.IGNORECASE)
    keywords = [k.lower() for k in conflict.get("key_keywords", [])]
    found: list[str] = []
    for entity in entities:
        if entity.entity_type != SPECIFICATION:
            continue
        if entity.input_type != source["input_type"]:
            continue
        if keywords and not any(k in entity.value.lower() for k in keywords):
            continue
        if pattern.search(entity.value):
            found.append(entity.value)
    return found


def score(
    conflicts: list[dict[str, Any]],
    entities: list[ExtractedEntity],
    inconsistencies: list[Inconsistency],
) -> BenchmarkReport:
    results: list[ConflictResult] = []
    used: set[int] = set()

    for conflict in conflicts:
        sources = conflict["sources"]
        matched = {
            f"{s['input_type']}#{i}": _matching_values(conflict, s, entities)
            for i, s in enumerate(sources)
        }
        with_values = [vals for vals in matched.values() if vals]

        if not with_values:
            status = NOT_EXTRACTED
        elif len(with_values) < len(sources):
            status = PARTIALLY_EXTRACTED
        else:
            status = EXTRACTED_NOT_FLAGGED
            for idx, inc in enumerate(inconsistencies):
                inc_values = set(inc.values)
                hits = sum(1 for vals in with_values if inc_values & set(vals))
                if hits >= 2:
                    status = DETECTED
                    used.add(idx)

        results.append(
            ConflictResult(
                conflict_id=conflict["id"],
                title=conflict["title"],
                status=status,
                decision=conflict.get("decision"),
                matched_values=matched,
            )
        )

    unmatched = [inc for idx, inc in enumerate(inconsistencies) if idx not in used]
    return BenchmarkReport(results=results, unmatched_inconsistencies=unmatched)


def format_report(report: BenchmarkReport) -> str:
    lines = [f"Detected {report.detected} of {report.total} (recall {report.recall:.0%})", ""]
    for r in report.results:
        lines.append(f"[{r.status}] {r.conflict_id}: {r.title}")
    if report.unmatched_inconsistencies:
        lines += ["", "Inconsistencies found by the system that are not in the known list:"]
        for inc in report.unmatched_inconsistencies:
            lines.append(f"  - {inc.key}: {' | '.join(inc.values)}")
    return "\n".join(lines)
