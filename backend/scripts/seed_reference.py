"""Ingest a reference .docx into the RAG knowledge base.

Usage:
    python -m backend.scripts.seed_reference path/to/reference.docx [--name "Template Name"]
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from config import settings
from core.database import AsyncSessionLocal
from models.template import ReferenceDocument
from rag.extractor import extract_docx
from rag.retriever import store_sections
from rag.splitter import split_sections


async def seed(path: str, name: str | None = None):
    doc_path = Path(path)
    if not doc_path.exists():
        raise FileNotFoundError(doc_path)

    print(f"Ingesting reference document: {doc_path}")
    sections = extract_docx(doc_path)
    print(f"  extracted {len(sections)} outline sections")

    rag_sections = split_sections(sections)
    print(f"  produced {len(rag_sections)} RAG sections")

    async with AsyncSessionLocal() as db:
        ref = ReferenceDocument(
            filename=doc_path.name,
            template_name=name or doc_path.stem,
            storage_path=str(doc_path),
            version=1,
            is_active=True,
            embedding_model=settings.embed_model,
            embedding_dimension=settings.embed_dimension,
        )
        db.add(ref)
        await db.flush()

        count = await store_sections(
            db=db,
            reference_doc_id=ref.id,
            template_name=ref.template_name,
            sections=rag_sections,
        )

    print(f"  stored {count} sections (ref id={ref.id})")
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Path to reference .docx")
    parser.add_argument("--name", help="Template name", default=None)
    args = parser.parse_args()
    asyncio.run(seed(args.path, args.name))
