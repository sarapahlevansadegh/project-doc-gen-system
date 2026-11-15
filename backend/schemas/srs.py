"""Pydantic schemas for generated SRS drafts.

Every sentence of a generated document is a Statement with exactly one
label, so a reviewer can see where it came from and what still needs an
engineer.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class StatementLabel(str, Enum):
    INPUT = "input"                # backed by one or more input chunks
    DECISION = "decision"          # taken from an engineer decision
    GENERAL_RULE = "general_rule"  # approved rule that fits any device
    PROPOSAL = "proposal"          # suggestion, needs engineer approval


class Statement(BaseModel):
    text: str
    label: StatementLabel
    chunk_ids: list[int] = Field(default_factory=list)
    decision_key: str | None = None
    needs_review: bool = False
    review_reason: str | None = None


class SectionDraft(BaseModel):
    section_id: str
    title: str
    status: str = "generated"      # "generated" | "needs_input"
    statements: list[Statement] = Field(default_factory=list)
