"""Demonstrate M1 pipeline on the Dental Laser fixture.

Prints:
  - example extracted outline sections (headings, hierarchy, types)
  - an in-memory sample retrieval (cosine over section embeddings)

No database required.
"""
from pathlib import Path

from rag.embeddings import embed_text
from rag.extractor import extract_docx
from rag.splitter import split_sections


def main():
    fixture = (
        Path(__file__).parent.parent.parent
        / "reference_templates"
        / "dental_laser_reference.docx"
    )
    sections = extract_docx(fixture)
    rag = split_sections(sections)

    print("=== EXTRACTED SECTIONS (outline preserved) ===")
    for s in sections:
        print(f"  [{s.level}] {s.heading_path}  (figures={len(s.figures)}, table={s.has_table})")

    print("\n=== RAG SECTIONS (named, typed, no blind chunking) ===")
    for r in rag:
        print(f"  {r.order:>2}. [{r.section_type:<11}] {r.section_name}")

    print("\n=== SAMPLE RETRIEVAL (in-memory cosine) ===")
    # embed all sections
    embeds = [(r, embed_text(r.content)) for r in rag]
    query = "LCD module display and touchscreen interaction"
    q = embed_text(query)
    import numpy as np

    def cos(a, b):
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    ranked = sorted(embeds, key=lambda x: cos(q, x[1]), reverse=True)
    print(f"  query: {query}\n")
    for r, _ in ranked[:3]:
        print(f"  -> {r.section_name}  [{r.section_type}]")


if __name__ == "__main__":
    main()
