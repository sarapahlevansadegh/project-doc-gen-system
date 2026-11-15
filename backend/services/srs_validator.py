"""Checks the label and evidence of generated SRS statements.

Pure code, no LLM. A statement that claims more than its evidence shows is
not dropped: it is downgraded to a proposal and flagged needs_review, so
unknown information is never presented as a fact. Two kinds of claim are
checked against the cited chunks: numbers, and names (button, widget, page
or class names such as "Power Slider" or "Class B"). The document body
keeps only statements that are not proposals; proposals go to an appendix
until an engineer approves them.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from schemas.srs import Statement, StatementLabel
from services.conflict_service import extract_number_tokens


_TERM_PATTERNS = (
    re.compile(r"\b(?:[A-Z][a-z0-9]+){2,}\b"),                 # CamelCase
    re.compile(r"\b[A-Z][A-Za-z0-9/&-]*(?:\s+[A-Z][A-Za-z0-9/&-]*)+\b"),  # Title Case phrase
    re.compile(r"\b[A-Z]{4,}\b"),                              # STANDBY
    re.compile(r"\bClass\s+[ABC]\b"),                          # software item class
)


def _squash(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", text.lower())


_LEADING_WORDS = frozenset({
    "the", "a", "an", "this", "that", "these", "those", "each", "every", "all",
    "if", "when", "after", "before", "in", "on", "for", "to", "of", "and", "or",
})


def _strip_leading_words(phrase: str) -> str:
    """"The Duty Cycle" -> "Duty Cycle": a capital letter at sentence start is not a name."""
    words = phrase.split()
    while words and words[0].lower() in _LEADING_WORDS:
        words.pop(0)
    return " ".join(words) if len(words) >= 2 else ""


def _unsupported_terms(text: str, evidence: Iterable[str]) -> list[str]:
    haystack = _squash(" ".join(evidence))
    found: dict[str, str] = {}
    for i, pattern in enumerate(_TERM_PATTERNS):
        for m in pattern.finditer(text):
            term = _strip_leading_words(m.group(0)) if i == 1 else m.group(0)
            if term:
                found.setdefault(_squash(term), term)
    return sorted(t for key, t in found.items() if key and key not in haystack)


def _flag(statement: Statement, reason: str) -> Statement:
    return statement.model_copy(update={
        "label": StatementLabel.PROPOSAL,
        "needs_review": True,
        "review_reason": reason,
    })


def _unsupported_numbers(text: str, evidence: Iterable[str]) -> list[str]:
    allowed: set[str] = set()
    for item in evidence:
        allowed |= extract_number_tokens(item)
    return sorted(extract_number_tokens(text) - allowed)


def validate_statement(
    statement: Statement,
    chunks: Mapping[int, str],
    decisions: Mapping[str, str] | None = None,
) -> Statement:
    decisions = decisions or {}
    if not statement.text.strip():
        return _flag(statement, "empty statement")

    if statement.label is StatementLabel.INPUT:
        if not statement.chunk_ids:
            return _flag(statement, "claimed from input but cites no chunk")
        unknown = [c for c in statement.chunk_ids if c not in chunks]
        if unknown:
            return _flag(statement, f"cites unknown chunk ids {unknown}")
        bad = _unsupported_numbers(
            statement.text, (chunks[c] for c in statement.chunk_ids)
        )
        if bad:
            return _flag(statement, f"numbers not found in cited chunks: {', '.join(bad)}")
        names = _unsupported_terms(statement.text, (chunks[c] for c in statement.chunk_ids))
        if names:
            return _flag(statement, f"names not found in cited chunks: {', '.join(names)}")
        return statement

    if statement.label is StatementLabel.DECISION:
        value = decisions.get(statement.decision_key or "")
        if value is None:
            return _flag(statement, "cites an engineer decision that does not exist")
        bad = _unsupported_numbers(statement.text, [value])
        if bad:
            return _flag(statement, f"numbers not in the decision: {', '.join(bad)}")
        names = _unsupported_terms(statement.text, [value])
        if names:
            return _flag(statement, f"names not in the decision: {', '.join(names)}")
        return statement

    if statement.label is StatementLabel.GENERAL_RULE:
        if extract_number_tokens(statement.text):
            return statement.model_copy(update={
                "needs_review": True,
                "review_reason": "numbers in a general rule are not checked against inputs",
            })
        return statement

    # PROPOSAL: always waits for an engineer.
    return statement.model_copy(update={
        "needs_review": True,
        "review_reason": statement.review_reason or "proposal, needs engineer approval",
    })


def validate_statements(
    statements: list[Statement],
    chunks: Mapping[int, str],
    decisions: Mapping[str, str] | None = None,
) -> list[Statement]:
    return [validate_statement(s, chunks, decisions) for s in statements]
