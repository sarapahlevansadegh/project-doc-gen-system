"""Phase 0: typed, multi-file device inputs.

Two layers, mirroring the rest of the suite:

* Service-level tests use a fake session and monkeypatched parser/chunker,
  so they need no database. They pin down what gets stored on the
  ``DeviceDocument`` row (input type, processing status/note) and the
  guard rails (unknown device, bad extension, several files of one type).
* One API-level test goes through the real HTTP layer and Postgres, same
  hermetic style as test_device_upload_pipeline.py (LLM and embedding model
  patched out, skipped when Postgres is unavailable).
"""
from __future__ import annotations

import io
import uuid

import pytest
from conftest import (
    cleanup_seeded_user,
    dispose_engine_sync,
    login_headers_sync,
    seed_admin_user,
)
from fastapi import HTTPException, UploadFile
from models.device_document import DeviceDocument
from schemas.device import DeviceDocumentOut, DeviceInputType
from services import device_document_parser, device_document_service, device_service


class _FakeDB:
    def __init__(self) -> None:
        self.added: list[DeviceDocument] = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        return None

    async def refresh(self, obj) -> None:
        return None


def _upload(filename: str, data: bytes = b"content") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=filename)


@pytest.fixture
def patched_service(monkeypatch, tmp_path):
    """Patch storage dir, device lookup, parser and chunker.

    Returns a dict the tests use to steer behaviour and observe calls.
    """
    state = {"section_count": 3, "device_exists": True, "chunk_calls": 0}

    monkeypatch.setattr(device_document_service, "DEVICE_DOCUMENTS_DIR", tmp_path)

    async def fake_get_device(db, device_id):
        return object() if state["device_exists"] else None

    async def fake_parse(db, document_id, storage_path):
        return state["section_count"]

    async def fake_chunks(db, document_id):
        state["chunk_calls"] += 1
        return 0  # 0 chunks -> ontology extraction is not attempted

    monkeypatch.setattr(device_service, "get_device", fake_get_device)
    monkeypatch.setattr(device_document_parser, "parse_and_store_sections", fake_parse)
    monkeypatch.setattr(device_document_service, "generate_and_store_chunks", fake_chunks)
    return state


async def test_attach_stores_input_type_and_parsed_status(patched_service):
    db = _FakeDB()
    await device_document_service.attach_document_to_device(
        db, uuid.uuid4(), _upload("gui.docx"), DeviceInputType.GUI_INPUT
    )
    doc = db.added[0]
    assert doc.input_type == "gui_input"
    assert doc.processing_status == "parsed"
    assert doc.processing_note is None
    assert patched_service["chunk_calls"] == 1


async def test_attach_pdf_is_skipped_with_conversion_note(patched_service):
    patched_service["section_count"] = 0
    db = _FakeDB()
    await device_document_service.attach_document_to_device(
        db, uuid.uuid4(), _upload("driver.pdf"), DeviceInputType.DRIVER_INPUT
    )
    doc = db.added[0]
    assert doc.input_type == "driver_input"
    assert doc.processing_status == "skipped"
    assert ".docx" in doc.processing_note
    assert patched_service["chunk_calls"] == 0


async def test_attach_docx_without_sections_is_failed(patched_service):
    patched_service["section_count"] = 0
    db = _FakeDB()
    await device_document_service.attach_document_to_device(
        db, uuid.uuid4(), _upload("broken.docx"), DeviceInputType.CONCEPT
    )
    assert db.added[0].processing_status == "failed"
    assert db.added[0].processing_note


async def test_attach_to_unknown_device_returns_404_and_stores_nothing(patched_service):
    patched_service["device_exists"] = False
    db = _FakeDB()
    with pytest.raises(HTTPException) as exc:
        await device_document_service.attach_document_to_device(
            db, uuid.uuid4(), _upload("gui.docx"), DeviceInputType.GUI_INPUT
        )
    assert exc.value.status_code == 404
    assert db.added == []


async def test_attach_rejects_unsupported_extension_before_device_lookup(patched_service):
    patched_service["device_exists"] = False  # would be 404 if lookup ran first
    db = _FakeDB()
    with pytest.raises(HTTPException) as exc:
        await device_document_service.attach_document_to_device(
            db, uuid.uuid4(), _upload("notes.txt"), DeviceInputType.OTHER
        )
    assert exc.value.status_code == 400
    assert db.added == []


async def test_two_files_of_same_type_are_both_kept(patched_service):
    db = _FakeDB()
    device_id = uuid.uuid4()
    for name in ("gui_r1.docx", "gui_r2.docx"):
        await device_document_service.attach_document_to_device(
            db, device_id, _upload(name), DeviceInputType.GUI_INPUT
        )
    assert [d.input_type for d in db.added] == ["gui_input", "gui_input"]
    assert len({d.id for d in db.added}) == 2


def test_document_out_exposes_new_fields_and_tolerates_legacy_rows():
    legacy = DeviceDocument(
        id=uuid.uuid4(),
        device_id=uuid.uuid4(),
        filename="old.docx",
        storage_path="x",
        file_size=1,
        content_type=None,
    )
    out = DeviceDocumentOut.model_validate(legacy)
    assert out.input_type is None
    assert out.processing_status is None

    typed = DeviceDocument(
        id=uuid.uuid4(),
        device_id=uuid.uuid4(),
        filename="new.docx",
        storage_path="x",
        file_size=1,
        content_type=None,
        input_type="concept",
        processing_status="parsed",
    )
    out = DeviceDocumentOut.model_validate(typed)
    assert (out.input_type, out.processing_status) == ("concept", "parsed")


def test_attach_endpoint_end_to_end():
    try:
        from agent.llm import LLMClient
        from app import app
        from fastapi.testclient import TestClient
        from rag import chunk_service
        from test_device_upload_pipeline import (
            _db_ok,
            _FakeEmbeddingService,
            _fake_llm_generate,
            _make_device_docx,
        )
    except ModuleNotFoundError:
        pytest.skip("async app stack / TestClient unavailable")

    import asyncio

    from core.database import AsyncSessionLocal, get_engine

    loop = asyncio.new_event_loop()
    admin_creds = None
    try:
        try:
            loop.run_until_complete(_db_ok(AsyncSessionLocal))
        except Exception as exc:
            if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
                pytest.skip("Postgres unavailable")
            raise
        admin_creds = seed_admin_user(loop)
    finally:
        try:
            loop.run_until_complete(get_engine().dispose())
        except Exception:
            pass
        loop.close()

    device_id: str | None = None
    docx_mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    try:
        with TestClient(app) as client:
            client.headers.update(login_headers_sync(client, *admin_creds))

            real_generate = LLMClient.generate
            real_embed_service = chunk_service.get_device_embedding_service
            LLMClient.generate = _fake_llm_generate
            chunk_service.get_device_embedding_service = lambda: _FakeEmbeddingService()
            try:
                created = client.post("/devices", json={"name": "Phase0 multi-input test"})
                assert created.status_code == 201, created.text
                device_id = created.json()["id"]

                # typed .docx -> parsed
                resp = client.post(
                    f"/devices/{device_id}/documents",
                    data={"input_type": "gui_input"},
                    files={"file": ("gui.docx", _make_device_docx(), docx_mime)},
                )
                assert resp.status_code == 201, resp.text
                docs = resp.json()["documents"]
                assert len(docs) == 1
                assert docs[0]["input_type"] == "gui_input"
                assert docs[0]["processing_status"] == "parsed"

                # second file of another type, a .pdf -> stored but skipped
                resp = client.post(
                    f"/devices/{device_id}/documents",
                    data={"input_type": "driver_input"},
                    files={"file": ("driver.pdf", b"%PDF-1.4 test", "application/pdf")},
                )
                assert resp.status_code == 201, resp.text
                by_type = {d["input_type"]: d for d in resp.json()["documents"]}
                assert set(by_type) == {"gui_input", "driver_input"}
                assert by_type["driver_input"]["processing_status"] == "skipped"

                # invalid type -> 422, unknown device -> 404
                bad = client.post(
                    f"/devices/{device_id}/documents",
                    data={"input_type": "banana"},
                    files={"file": ("x.docx", _make_device_docx(), docx_mime)},
                )
                assert bad.status_code == 422
                missing = client.post(
                    f"/devices/{uuid.uuid4()}/documents",
                    data={"input_type": "concept"},
                    files={"file": ("x.docx", _make_device_docx(), docx_mime)},
                )
                assert missing.status_code == 404
            finally:
                LLMClient.generate = real_generate
                chunk_service.get_device_embedding_service = real_embed_service
    finally:
        if admin_creds:
            cleanup_seeded_user(admin_creds[0])
        if device_id:

            async def _cleanup():
                from models.device import Device
                from models.ontology import OntologyEntity

                async with AsyncSessionLocal() as db:
                    await db.execute(
                        OntologyEntity.__table__.delete().where(
                            OntologyEntity.device_id == uuid.UUID(device_id)
                        )
                    )
                    dev = await db.get(Device, uuid.UUID(device_id))
                    if dev is not None:
                        await db.delete(dev)
                    await db.commit()

            try:
                asyncio.run(_cleanup())
            except Exception:
                pass

    dispose_engine_sync()
