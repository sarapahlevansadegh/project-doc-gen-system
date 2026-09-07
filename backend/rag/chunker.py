"""Phase 3 chunking pipeline: turn one device_document_sections row into
one or more RAG-ready chunks.

Design decisions (agreed before implementation):
- Unit of chunking is the section (already split by rag/splitter.py in
  Phase 2.5). We only split *further* within a section when it exceeds
  ``max_tokens`` for the embedding model (BAAI/bge-base-en-v1.5).
- A Markdown table (see rag/extractor.py's _table_to_markdown) is never
  split across two chunks - it is always kept as one atomic block, even if
  that occasionally makes a chunk exceed max_tokens. A half-table is
  useless for retrieval; a slightly-oversized chunk is not.
- A section with no body content (a pure structural heading, e.g. a
  top-level "Standard Requirements" heading whose only content lives under
  its child heading) produces no chunk of its own. Its title is instead
  carried forward as breadcrumb context on every chunk of the sections
  under it, via `parent_section` (already stored per section - see
  models/device_document.py). This avoids inventing a cross-section
  content merge that the document_chunks schema (one chunk -> exactly one
  section_id) can't represent cleanly.
- Every chunk is prefixed with its own section's breadcrumb
  ("Parent > Section Name") so it reads coherently when retrieved on its
  own, out of order, by a vector search.
- Overlap between consecutive chunks of an oversized section is
  token-based (not char-based) and reuses the same token counter as the
  size limit, so it's consistent with whatever tokenizer the embedding
  model actually uses.

Token counting is injected (``token_counter``) rather than hardcoded to a
specific tokenizer import, so:
  1. these are pure, fast unit tests with no torch/transformers dependency.
  2. production code passes the *actual* bge-base-en-v1.5 tokenizer (see
     ``bge_token_counter()`` below) so chunk sizes are accurate for the
     model that will embed them, not an approximation.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

TokenCounter = Callable[[str], int]

DEFAULT_MAX_TOKENS = 512
DEFAULT_OVERLAP_RATIO = 0.125  # ~10-15% of max_tokens, per agreed design

_TABLE_LINE_RE = re.compile(r"^\|.*\|\s*$")


@dataclass
class Chunk:
    text: str
    token_count: int
    index: int  # 0-based, local to this section


def _approx_word_token_counter(text: str) -> int:
    """Fallback counter (~1 token per word) for callers that don't need
    exact tokenizer alignment, e.g. quick scripts/debugging. Production
    chunk generation should use ``bge_token_counter()`` instead so stored
    ``token_count`` values match what the embedding model actually sees."""
    return len(text.split())


def bge_token_counter() -> TokenCounter:
    """Build a token counter backed by the real embedding model's tokenizer.

    Imports sentence-transformers lazily (heavy: pulls torch) so this stays
    out of the hot path for anything that doesn't actually need it - unit
    tests for chunk-packing logic should pass their own lightweight counter
    instead of calling this.
    """
    from rag.device_embedding_service import get_device_embedding_service

    tokenizer = get_device_embedding_service().model.tokenizer

    def _count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    return _count


def _split_into_blocks(content: str) -> list[str]:
    """Split section content into atomic blocks: a Markdown table is one
    block (never split further downstream); everything else is split on
    blank lines into paragraph-sized blocks."""
    blocks: list[str] = []
    lines = content.split("\n")
    buf: list[str] = []
    in_table = False

    def _flush_buf() -> None:
        text = "\n".join(buf).strip()
        if text:
            blocks.append(text)
        buf.clear()

    for line in lines:
        is_table_line = bool(_TABLE_LINE_RE.match(line.strip()))
        if is_table_line:
            if not in_table:
                # starting a table - flush whatever paragraph text preceded it
                _flush_buf()
                in_table = True
            buf.append(line)
            continue
        if in_table:
            # table ended
            _flush_buf()
            in_table = False
        if line.strip() == "":
            _flush_buf()
        else:
            buf.append(line)
    _flush_buf()
    return blocks


def _split_oversized_paragraph(
    text: str, max_tokens: int, token_counter: TokenCounter
) -> list[str]:
    """Fall back to sentence/word-boundary splitting for a single paragraph
    that alone exceeds max_tokens (rare for section text, but handled for
    robustness). Never used for table blocks - those stay whole regardless
    of size, per the no-mid-table-split rule."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = token_counter(sentence)
        if current and current_tokens + sentence_tokens > max_tokens:
            pieces.append(" ".join(current))
            current = []
            current_tokens = 0
        if sentence_tokens > max_tokens:
            # a single sentence alone is too long - last resort: hard word split
            words = sentence.split(" ")
            word_buf: list[str] = []
            word_tokens = 0
            for word in words:
                wt = token_counter(word)
                if word_buf and word_tokens + wt > max_tokens:
                    pieces.append(" ".join(word_buf))
                    word_buf = []
                    word_tokens = 0
                word_buf.append(word)
                word_tokens += wt
            if word_buf:
                pieces.append(" ".join(word_buf))
            continue
        current.append(sentence)
        current_tokens += sentence_tokens

    if current:
        pieces.append(" ".join(current))
    return pieces


def _pack_blocks(
    blocks: list[str],
    max_tokens: int,
    overlap_tokens: int,
    token_counter: TokenCounter,
) -> list[list[str]]:
    """Greedily pack atomic blocks into groups (future chunks), each as
    close to max_tokens as possible without exceeding it - except a single
    table block, which is always kept whole even if it alone exceeds
    max_tokens (see module docstring). Consecutive groups repeat trailing
    blocks from the previous group up to overlap_tokens, so context isn't
    lost across a chunk boundary."""
    groups: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = token_counter(block)
        is_table = block.lstrip().startswith("|")

        if not is_table and block_tokens > max_tokens:
            # oversized plain-text block: split it internally first
            for piece in _split_oversized_paragraph(block, max_tokens, token_counter):
                piece_tokens = token_counter(piece)
                if current and current_tokens + piece_tokens > max_tokens:
                    groups.append(current)
                    current = _carry_overlap(current, overlap_tokens, token_counter)
                    current_tokens = sum(token_counter(b) for b in current)
                current.append(piece)
                current_tokens += piece_tokens
            continue

        if current and current_tokens + block_tokens > max_tokens:
            groups.append(current)
            current = _carry_overlap(current, overlap_tokens, token_counter)
            current_tokens = sum(token_counter(b) for b in current)

        current.append(block)
        current_tokens += block_tokens

    if current:
        groups.append(current)
    return groups


def _carry_overlap(
    prev_group: list[str], overlap_tokens: int, token_counter: TokenCounter
) -> list[str]:
    """Pick trailing blocks from the previous chunk to seed the next one,
    up to overlap_tokens. Tables are never carried as overlap filler - an
    already-complete table repeated purely for overlap padding adds cost
    without adding retrieval value; overlap is meant for prose continuity."""
    carried: list[str] = []
    budget = overlap_tokens
    for block in reversed(prev_group):
        if block.lstrip().startswith("|"):
            break  # stop at a table boundary; don't reach past it for overlap
        cost = token_counter(block)
        if cost > budget:
            break
        carried.insert(0, block)
        budget -= cost
    return carried


def chunk_section(
    section_name: str,
    parent_section: str | None,
    content: str,
    token_counter: TokenCounter | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_ratio: float = DEFAULT_OVERLAP_RATIO,
) -> list[Chunk]:
    """Split one section's content into RAG-ready chunks.

    Returns an empty list for a section with no body content (a pure
    structural heading) - see module docstring for why that's intentional
    rather than a bug.
    """
    if not content or not content.strip():
        return []

    token_counter = token_counter or _approx_word_token_counter
    overlap_tokens = max(1, int(max_tokens * overlap_ratio))

    breadcrumb = f"{parent_section} > {section_name}" if parent_section else section_name

    # The breadcrumb is prepended to every chunk's final text (below), but
    # _pack_blocks() only sees the body blocks - without reserving its
    # budget here, a section with a long breadcrumb (e.g. a deep heading
    # path) could pack blocks right up to max_tokens and then exceed it
    # once the breadcrumb is added on top. Seen in practice: a chunk came
    # out to 519 tokens against a 512 max, which triggered a real crash in
    # the embedding model's CPU inference on the oversized sequence (see
    # docker-compose.yml's OMP_NUM_THREADS note) - so this isn't just a
    # cosmetic over-budget, it fed an input the embedding step couldn't
    # safely handle.
    breadcrumb_tokens = token_counter(breadcrumb + "\n\n")
    body_max_tokens = max(1, max_tokens - breadcrumb_tokens)

    blocks = _split_into_blocks(content)
    if not blocks:
        return []

    groups = _pack_blocks(blocks, body_max_tokens, overlap_tokens, token_counter)

    chunks: list[Chunk] = []
    for i, group in enumerate(groups):
        text = f"{breadcrumb}\n\n" + "\n\n".join(group)
        chunks.append(Chunk(text=text, token_count=token_counter(text), index=i))
    return chunks
