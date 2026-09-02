"""Extract embedded image bytes from a Device DOCX's zip package (Phase 2.5, Part B).

``rag.extractor.extract_docx`` already detects each embedded image and
records a reference to it (``rel_id``, ``alt_text``, size) via the
``FigureRef`` dataclass - but not the image bytes themselves. A ``.docx``
file is just a zip archive: every embedded image lives under
``word/media/`` and is linked to a run through the relationship id
declared in ``word/_rels/document.xml.rels``. This module resolves that
relationship and writes the real image bytes to disk, so a figure
reference can point at an actual file instead of just an in-document id.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

DEVICE_DOCUMENT_IMAGES_DIR = Path("device_documents/images")
DEVICE_DOCUMENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

_RELS_PATH = "word/_rels/document.xml.rels"
_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _load_relationship_map(zf: zipfile.ZipFile) -> dict[str, str]:
    """Map rel_id -> target path (relative to ``word/``) from document.xml.rels."""
    try:
        data = zf.read(_RELS_PATH)
    except KeyError:
        # A relationships part missing entirely means a malformed/unusual
        # docx - treat as "no images resolvable" rather than raising.
        logger.warning("No %s found in docx package", _RELS_PATH)
        return {}

    root = ET.fromstring(data)
    mapping: dict[str, str] = {}
    for rel in root.findall(f"{_REL_NS}Relationship"):
        rel_id = rel.get("Id")
        target = rel.get("Target")
        if rel_id and target:
            mapping[rel_id] = target
    return mapping


def extract_images(
    docx_path: str | Path,
    document_id,
    rel_ids: set[str],
) -> dict[str, str]:
    """Extract the embedded images referenced by ``rel_ids`` from a .docx.

    Returns a mapping of ``rel_id -> saved file path`` for whichever ids
    were actually found and successfully extracted. A missing relationship,
    a target absent from the zip, or a corrupt/non-zip file are all logged
    and skipped rather than raised - one bad image must not block parsing
    of the rest of the document (mirrors the fail-soft behavior already
    used in ``device_document_parser.parse_and_store_sections``).
    """
    if not rel_ids:
        return {}

    saved: dict[str, str] = {}
    out_dir = DEVICE_DOCUMENT_IMAGES_DIR / str(document_id)

    try:
        with zipfile.ZipFile(docx_path) as zf:
            rel_map = _load_relationship_map(zf)
            if not rel_map:
                return {}

            out_dir.mkdir(parents=True, exist_ok=True)

            for rel_id in rel_ids:
                target = rel_map.get(rel_id)
                if not target:
                    logger.warning(
                        "rel_id %s not found in %s for %s", rel_id, _RELS_PATH, docx_path
                    )
                    continue

                # Targets are stored relative to word/, e.g. "media/image1.png"
                member = target if target.startswith("word/") else f"word/{target}"
                member = member.lstrip("/")
                try:
                    blob = zf.read(member)
                except KeyError:
                    logger.warning(
                        "Image member %s (rel %s) missing from %s", member, rel_id, docx_path
                    )
                    continue

                ext = Path(member).suffix or ".bin"
                dest = out_dir / f"{rel_id}{ext}"
                dest.write_bytes(blob)
                saved[rel_id] = str(dest)
    except (zipfile.BadZipFile, FileNotFoundError, OSError):
        logger.exception(
            "Failed to open %s as a docx zip package for image extraction", docx_path
        )
        return {}

    return saved
