"""Unit tests for rag/chunker.py.

Uses a simple word-count token counter throughout (not the real bge
tokenizer) so these are fast, dependency-free tests of the packing logic
itself. bge_token_counter() is exercised separately/manually since it
imports sentence-transformers (torch).
"""
from __future__ import annotations

from rag.chunker import chunk_section


def _word_counter(text: str) -> int:
    return len(text.split())


def test_empty_content_produces_no_chunks():
    assert chunk_section("Standard Requirements", None, "", _word_counter) == []
    assert chunk_section("Standard Requirements", None, "   \n  ", _word_counter) == []


def test_small_section_is_a_single_chunk_with_breadcrumb():
    chunks = chunk_section(
        "Splash Page",
        "General Design requirements",
        "The splash screen shows the logo for three seconds.",
        _word_counter,
        max_tokens=512,
    )
    assert len(chunks) == 1
    assert chunks[0].text.startswith("General Design requirements > Splash Page\n\n")
    assert "splash screen shows the logo" in chunks[0].text


def test_no_parent_section_breadcrumb_is_just_the_title():
    chunks = chunk_section("Intro", None, "Some intro text.", _word_counter)
    assert chunks[0].text.startswith("Intro\n\n")


def test_oversized_section_splits_into_multiple_chunks():
    # 6 paragraphs of 30 words each = 180 words; max_tokens=50 forces a split
    paragraph = " ".join(f"word{i}" for i in range(30))
    content = "\n\n".join([paragraph] * 6)

    chunks = chunk_section(
        "Settings Page", "Home Page", content, _word_counter, max_tokens=50, overlap_ratio=0.1
    )

    assert len(chunks) > 1
    for c in chunks:
        # breadcrumb itself costs a few tokens; allow some headroom but each
        # chunk should still be roughly bounded, not just one giant blob
        assert c.token_count <= 50 + 10


def test_consecutive_chunks_share_overlap_text():
    # short paragraphs so the overlap budget can comfortably fit one whole
    # block (overlap operates at block granularity, not word-by-word)
    para_a = " ".join(f"word{i}" for i in range(5))
    para_b = " ".join(f"mid{i}" for i in range(5))
    para_c = " ".join(f"other{i}" for i in range(5))
    content = "\n\n".join([para_a, para_b, para_c])

    chunks = chunk_section(
        "Settings Page", None, content, _word_counter, max_tokens=6, overlap_ratio=0.9
    )
    assert len(chunks) >= 2
    # para_b ends chunk 0 (alone, since max_tokens=6 fits one 5-word block)
    # and should be carried into chunk 1 as overlap context.
    first_body = chunks[0].text.split("\n\n", 1)[1]
    second_body = chunks[1].text.split("\n\n", 1)[1]
    assert first_body.strip() in second_body


def test_table_is_never_split_across_chunks():
    table = "\n".join(
        ["| Parameter | Value |", "| --- | --- |"]
        + [f"| Param{i} | {i} |" for i in range(40)]
    )
    content = "Intro paragraph before the table.\n\n" + table

    chunks = chunk_section(
        "Specifications", None, content, _word_counter, max_tokens=30, overlap_ratio=0.1
    )

    # the full table must appear intact in exactly one chunk
    table_chunks = [c for c in chunks if table in c.text]
    assert len(table_chunks) == 1


def test_table_is_kept_whole_even_if_it_alone_exceeds_max_tokens():
    table = "\n".join(
        ["| Parameter | Value |", "| --- | --- |"]
        + [f"| Param{i} | {i} |" for i in range(200)]
    )
    chunks = chunk_section("Specifications", None, table, _word_counter, max_tokens=50)

    assert len(chunks) == 1
    assert table in chunks[0].text


def test_overlap_does_not_reach_across_a_table_boundary():
    table = "\n".join(["| A | B |", "| --- | --- |", "| 1 | 2 |"])
    para_before_table = " ".join(f"w{i}" for i in range(10))
    para_after_table = " ".join(f"x{i}" for i in range(30))
    content = f"{para_before_table}\n\n{table}\n\n{para_after_table}"

    chunks = chunk_section(
        "Mixed Section", None, content, _word_counter, max_tokens=15, overlap_ratio=0.5
    )

    # whichever chunk starts after the table must not have carried the
    # pre-table paragraph as overlap filler across the table
    for c in chunks:
        if table not in c.text and para_after_table.split()[0] in c.text:
            assert para_before_table not in c.text


def test_oversized_single_paragraph_falls_back_to_sentence_split():
    long_sentence_paragraph = ". ".join(f"Sentence number {i} is here" for i in range(20)) + "."
    chunks = chunk_section(
        "Help Page", None, long_sentence_paragraph, _word_counter, max_tokens=20
    )
    assert len(chunks) > 1
    for c in chunks:
        assert c.token_count <= 20 + 10
