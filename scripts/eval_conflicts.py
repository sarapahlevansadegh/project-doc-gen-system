"""Run the known-conflicts benchmark against a device in the dev database.

From the repo root, with DATABASE_URL set:

    uv run --no-sync python scripts/eval_conflicts.py \
        --device-id <uuid> \
        --known backend/tests/fixtures/vl8_known_conflicts.json

Read-only: it only queries ontology_entities, document_chunks and
device_documents. It compares two methods on the same stored entities:

  old  check_ontology_consistency (same exact name in the same device)
  new  services/cross_file_conflicts.find_conflicts (names normalised,
       numbers compared after unit scaling, alarms compared field by field)

It does not run the ontology extraction itself. If the device has no
Specification entities yet, it lists the documents so you can run
POST /devices/documents/{document_id}/ontology for each one.

Known limit: ontology_entities is unique on (device_id, entity_type, value),
so a value that appears identically in two input files is stored once and
is attributed to the first chunk that produced it. Conflicting values are
different strings, so this does not hide real conflicts.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

import models  # noqa: E402,F401  (registers every mapper)
from core.database import AsyncSessionLocal  # noqa: E402
from models.device_document import DeviceDocument  # noqa: E402
from models.document_chunk import DocumentChunk  # noqa: E402
from models.ontology import OntologyEntity  # noqa: E402
from services.conflict_benchmark import (  # noqa: E402
    DETECTED,
    ExtractedEntity,
    Inconsistency,
    format_report,
    load_known_conflicts,
    score,
)
from services.cross_file_conflicts import (  # noqa: E402
    CROSS_FILE,
    UNPAIRED_ALARM,
    WITHIN_FILE,
    SourcedValue,
    find_conflicts,
)
from services.document_diff_planner import check_ontology_consistency  # noqa: E402
from sqlalchemy import select  # noqa: E402


async def load_documents(db, device_id: uuid.UUID):
    stmt = select(
        DeviceDocument.id,
        DeviceDocument.input_type,
        DeviceDocument.filename,
        DeviceDocument.processing_status,
    ).where(DeviceDocument.device_id == device_id)
    return (await db.execute(stmt)).all()


async def load_entities(db, device_id: uuid.UUID) -> list[ExtractedEntity]:
    stmt = (
        select(
            OntologyEntity.entity_type,
            OntologyEntity.value,
            DeviceDocument.input_type,
        )
        .outerjoin(DocumentChunk, OntologyEntity.source_chunk_id == DocumentChunk.id)
        .outerjoin(
            DeviceDocument, DocumentChunk.device_document_id == DeviceDocument.id
        )
        .where(OntologyEntity.device_id == device_id)
    )
    rows = (await db.execute(stmt)).all()
    return [ExtractedEntity(t, v, it or "") for t, v, it in rows]


def _clip(text: str, width: int = 110) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def _print_findings(title: str, findings) -> None:
    print(f"\n{title} ({len(findings)})")
    for f in findings:
        print(f"  - {f.key}  [{f.note}]")
        for input_type, value in f.values:
            print(f"      {input_type}: {_clip(value)}")


async def main(device_id: uuid.UUID, known_path: Path, show_entities: bool) -> int:
    conflicts = load_known_conflicts(known_path)

    async with AsyncSessionLocal() as db:
        documents = await load_documents(db, device_id)
        if not documents:
            print(f"No documents found for device {device_id}. Check the UUID.")
            return 1

        print("Documents of this device:")
        for doc_id, input_type, filename, status in documents:
            print(f"  {doc_id}  {input_type or '-':16} {status or '-':8} {filename}")

        entities = await load_entities(db, device_id)
        specs = [e for e in entities if e.entity_type == "Specification"]
        no_source = sum(1 for e in specs if not e.input_type)
        print(
            f"\nOntology entities: {len(entities)} total, {len(specs)} Specification, "
            f"{no_source} Specification without a source file"
        )

        if not specs:
            print(
                "\nNo Specification entities yet, so there is nothing to score.\n"
                "Run the ontology extraction once per document id above:\n"
                "  POST /devices/documents/{document_id}/ontology\n"
                "(http://localhost:8000/docs, press Authorize first, then try it out.)\n"
                "Then run this script again."
            )
            return 1

        old_found = await check_ontology_consistency(db, device_id)
        old_inconsistencies = [Inconsistency(i.key, tuple(i.values)) for i in old_found]

    if show_entities:
        print("\nSpecification entities by input type:")
        for e in sorted(specs, key=lambda e: (e.input_type, e.value)):
            print(f"  [{e.input_type or '-'}] {e.value}")

    findings = find_conflicts(
        [SourcedValue(e.value, e.input_type) for e in specs if e.input_type]
    )
    cross = [f for f in findings if f.kind == CROSS_FILE]
    within = [f for f in findings if f.kind == WITHIN_FILE]
    unpaired = [f for f in findings if f.kind == UNPAIRED_ALARM]

    old_report = score(conflicts, entities, old_inconsistencies)
    new_report = score(conflicts, entities, [f.to_inconsistency() for f in cross])

    print(
        f"\nOld method (exact name): detected {old_report.detected} of {old_report.total}"
        f"\nNew method (cross-file): detected {new_report.detected} of {new_report.total}"
        f" (recall {new_report.recall:.0%})\n"
    )
    print(format_report(new_report))

    print("\nDetails for conflicts that the new method did not detect:")
    for result in new_report.results:
        if result.status == DETECTED:
            continue
        sources = ", ".join(
            f"{name.split('#')[0]}: {len(vals)} match(es)"
            for name, vals in result.matched_values.items()
        )
        print(f"  {result.conflict_id}: {sources}")

    _print_findings("Conflicts between files (for engineer review)", cross)
    _print_findings("Same label, different values inside one file", within)
    _print_findings("Alarms found in only one file", unpaired)
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device-id", required=True, type=uuid.UUID)
    parser.add_argument("--known", required=True, type=Path)
    parser.add_argument(
        "--show-entities",
        action="store_true",
        help="also print every Specification entity with its input type",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.device_id, args.known, args.show_entities)))
