"""Section-by-section SRS draft generation.

Pure code around an LLM object that has
``generate(prompt, max_tokens, temperature) -> str`` (agent.llm.LLMClient
fits, and tests pass a fake). Database access lives in srs_inputs.py.

For each section recipe the generator gives the model the device's input
chunks (numbered, so it can cite them) and the engineer decisions, asks for
a JSON list of labelled statements, and runs the result through
srs_validator so a claim without evidence becomes a flagged proposal.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from schemas.srs import SectionDraft, Statement, StatementLabel
from services.srs_recipes import FIXED_TEXT, SectionRecipe, recipes_for_device
from services.srs_validator import validate_statements

# Input budget per section (characters). Lower it (env DOCGEN_SRS_MAX_CHARS) for providers
# with a small tokens-per-minute limit; chunks that do not fit are reported, not hidden.
MAX_INPUT_CHARS = int(os.environ.get("DOCGEN_SRS_MAX_CHARS", "30000"))
# Output budget per section. Lower it (env DOCGEN_SRS_MAX_TOKENS) on a small provider balance.
MAX_TOKENS = int(os.environ.get("DOCGEN_SRS_MAX_TOKENS", "8000"))
# Sampling temperature. 0 is best for exact extraction; some newer models want their default.
TEMPERATURE = float(os.environ.get("DOCGEN_SRS_TEMPERATURE", "0.0"))
ATTEMPTS = 2


class TextGenerator(Protocol):
    def generate(self, prompt: str, max_tokens: int = ..., temperature: float = ...) -> str: ...


@dataclass(frozen=True)
class InputChunk:
    id: int
    input_type: str
    section_name: str | None
    text: str


def load_decisions_file(path) -> dict[str, str]:
    """Read {"decisions": {key: value}} written by the engineer's decisions."""
    from pathlib import Path

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data["decisions"].items()}


def _format_chunks(chunks: list[InputChunk]) -> str:
    parts = []
    for c in chunks:
        where = f"{c.input_type} / {c.section_name}" if c.section_name else c.input_type
        parts.append(f"[C{c.id}] ({where})\n{c.text}")
    return "\n\n".join(parts)


def build_prompt(
    recipe: SectionRecipe, chunks: list[InputChunk], decisions: dict[str, str]
) -> str:
    decision_lines = "\n".join(f"- {k}: {v}" for k, v in decisions.items()) or "(none)"
    return f"""You write one section of a Software Requirements Specification (SRS) for a medical device.

Section: {recipe.id} {recipe.title}
Form: {recipe.form}
Style: {recipe.guidance}

Rules:
- Use only facts found in the INPUT CHUNKS or in the ENGINEER DECISIONS below. Never use outside knowledge about this device.
- Write short, testable sentences ("The software shall ..." or "Capability to ...").
- Return ONLY a JSON array. Each item: {{"text": string, "label": "input" | "decision" | "general_rule" | "proposal", "chunk_ids": [integer], "decision_key": string or null}}
- label "input": cite every chunk id the sentence relies on (the number after C). Every number in the sentence must appear in a cited chunk.
- label "decision": when an engineer decision answers the point, cite its key and use its value. Engineer decisions override the chunks.
- label "general_rule": only for sentences that fit any device and contain no numbers.
- label "proposal": for anything that seems needed but the inputs do not say. Never state it as a fact.
- Do not introduce names of buttons, widgets, pages, files, classes or software items that do not appear in the chunks. Do not state a software item class (Class A, B or C) unless a chunk does.
- Do not number the sentences. For tables write one sentence per row: "Column: value; Column: value".
- If the inputs say nothing useful for this section, return [].

ENGINEER DECISIONS:
{decision_lines}

INPUT CHUNKS:
{_format_chunks(chunks)}
"""


def parse_statements(raw: str) -> list[Statement]:
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()  # reasoning models
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except ValueError:
        # the model may add a sentence before or after the array
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            raise
        data = json.loads(text[start : end + 1])
    if isinstance(data, dict):
        data = data.get("statements", [])
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of statements")
    out: list[Statement] = []
    for item in data:
        label = item.get("label")
        valid = label in {m.value for m in StatementLabel}
        out.append(Statement(
            text=str(item.get("text", "")),
            label=StatementLabel(label) if valid else StatementLabel.PROPOSAL,
            chunk_ids=[int(c) for c in item.get("chunk_ids") or []],
            decision_key=item.get("decision_key"),
            needs_review=not valid,
            review_reason=None if valid else f"unknown label {label!r}",
        ))
    return out


def _needs_input(recipe: SectionRecipe, reason: str) -> SectionDraft:
    return SectionDraft(
        section_id=recipe.id,
        title=recipe.title,
        status="needs_input",
        statements=[Statement(
            text="No usable input for this section. Engineer input is required.",
            label=StatementLabel.PROPOSAL,
            needs_review=True,
            review_reason=reason,
        )],
    )


def _select_chunks(
    recipe: SectionRecipe, chunks: list[InputChunk], max_chars: int
) -> tuple[list[InputChunk], int]:
    order = {t: i for i, t in enumerate(recipe.input_types)}
    relevant = sorted(
        (c for c in chunks if c.input_type in order),
        key=lambda c: (order[c.input_type], c.id),
    )
    selected: list[InputChunk] = []
    used = 0
    for c in relevant:
        if used + len(c.text) > max_chars and selected:
            break
        selected.append(c)
        used += len(c.text)
    return selected, len(relevant) - len(selected)


def generate_section(
    recipe: SectionRecipe,
    chunks: list[InputChunk],
    decisions: dict[str, str],
    llm: TextGenerator,
    max_chars: int = MAX_INPUT_CHARS,
) -> SectionDraft:
    if recipe.mode == FIXED_TEXT:
        return SectionDraft(
            section_id=recipe.id,
            title=recipe.title,
            statements=[Statement(text=recipe.fixed_text or "",
                                  label=StatementLabel.GENERAL_RULE)],
        )

    selected, skipped = _select_chunks(recipe, chunks, max_chars)
    if not selected:
        return _needs_input(recipe, "no input chunks of the required types")

    prompt = build_prompt(recipe, selected, decisions)
    statements: list[Statement] | None = None
    last_error = ""
    for _ in range(ATTEMPTS):
        raw = llm.generate(prompt, MAX_TOKENS, TEMPERATURE)
        try:
            statements = parse_statements(raw)
            break
        except (ValueError, TypeError, AttributeError) as exc:   # JSON or shape errors
            start = " ".join(raw.split())[:200]
            last_error = f"{exc}; reply began: {start!r}; reply length {len(raw)}"
    if statements is None:
        return _needs_input(recipe, f"model output could not be read: {last_error}")
    if not statements:
        return _needs_input(recipe, "the inputs say nothing for this section")

    statements = validate_statements(
        statements, {c.id: c.text for c in selected}, decisions
    )
    if skipped:
        statements.append(Statement(
            text=f"{skipped} input chunk(s) did not fit and were not used. "
                 "This section may be incomplete.",
            label=StatementLabel.PROPOSAL,
            needs_review=True,
            review_reason="input truncated",
        ))
    return SectionDraft(section_id=recipe.id, title=recipe.title, statements=statements)


def generate_srs_from_chunks(
    chunks: list[InputChunk],
    llm: TextGenerator,
    decisions: dict[str, str] | None = None,
    include_optional: bool = False,
    max_chars: int = MAX_INPUT_CHARS,
) -> list[SectionDraft]:
    decisions = decisions or {}
    available = {c.input_type for c in chunks}
    return [
        generate_section(r, chunks, decisions, llm, max_chars)
        for r in recipes_for_device(available, include_optional)
    ]


def summarize(drafts: list[SectionDraft]) -> dict:
    labels: Counter[str] = Counter()
    review = 0
    for d in drafts:
        for s in d.statements:
            labels[s.label.value] += 1
            review += s.needs_review
    return {
        "sections": len(drafts),
        "sections_needing_input": sum(d.status == "needs_input" for d in drafts),
        "statements": sum(labels.values()),
        "by_label": dict(labels),
        "needs_review": review,
    }
