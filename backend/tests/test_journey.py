"""End-to-end user journey integration test (Milestone 5.2).

Exercises the full API flow with no real LLM or embedding model:
  1. Create a Device
  2. Upload a reference .docx (RAG extraction + embedding stored)
  3. Verify reference + RAG sections persisted
  4. Upload a device .docx (sections + chunks + ontology, now automatic)
  5. Start document generation
  6. Verify background job lifecycle
  7. Connect to WebSocket progress and verify payload
  8. Wait until generation completes
  9. Download the generated DOCX
  10. Verify the file exists and is a valid .docx

The real LLM and embedding calls are replaced with deterministic
implementations via monkeypatch (same spirit as the mocked-LLM tests in
test_agent.py) so the journey runs hermetically against Postgres.

Step 4 (device document upload) is not optional here: services/
document_generator.py - what /documents/generate now actually runs, see
services/generation_service.py - needs a real device_document_id to match
against, unlike the older agent/workflow.py path this journey used to
exercise, which could generate from a bare Device row's own specs/alarms/
commands fields alone with no uploaded document at all.
"""
from __future__ import annotations

import io
import json
import time

import pytest
from conftest import (
    cleanup_seeded_user,
    dispose_engine_sync,
    login_headers_sync,
    seed_admin_user,
)
from docx import Document as DocxDocument

EMBED_DIM = 768  # matches settings.embed_dimension / BAAI/bge-base-en-v1.5 (Phase 3);
                 # was 384 (stale MiniLM-L6-v2 value), which made every
                 # /rag/reference upload in this test fail with
                 # "expected 768 dimensions, not 384" against the real
                 # pgvector(768) column


def _fake_llm(self, prompt: str, max_tokens: int, temperature: float) -> str:
    # ontology/extractor.py's relationship prompt always embeds "ENTITIES:"
    if "ENTITIES:" in prompt:
        return "[]"
    # services/document_diff_planner.py's section prompt (used by both the
    # /plan endpoint and services/document_generator.py) always includes
    # this heading, and always wants a JSON object back - deterministically
    # "no change" here since this journey only checks the job lifecycle
    # and download work, not particular replaced content (that's
    # test_document_diff_planner.py's and test_document_generator.py's job).
    if "REFERENCE SECTION" in prompt:
        return json.dumps(
            {
                "changed": False,
                "reason": "journey test stub - no device-specific replacement",
                "new_paragraphs": None,
                "new_table_markdown": None,
            }
        )
    # ontology entity-extraction prompt
    return "[]"


async def _fake_embed(text: str) -> list[float]:
    # deterministic fixed-dimension vector (matches Vector(768) column)
    return [0.0] * EMBED_DIM


class _FakeDeviceEmbeddingService:
    def embed_documents(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        return [[0.0] * EMBED_DIM for _ in texts]


def _make_reference_docx() -> bytes:
    doc = DocxDocument()
    doc.add_heading("1. Architecture of Software", level=1)
    doc.add_paragraph("The device runs a layered software architecture.")
    doc.add_heading("1.1 LCD Module", level=2)
    doc.add_paragraph("The LCD module renders status and warnings.")
    doc.add_heading("2. Serial Communication Architecture", level=1)
    doc.add_paragraph("Serial link uses RS-232 at 115200 baud.")
    doc.add_heading("7. Software Specifications", level=1)
    doc.add_paragraph("Driver and Qt specifications table.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _make_device_docx() -> bytes:
    doc = DocxDocument()
    doc.add_heading("1. Architecture of Software", level=1)
    doc.add_paragraph("The VL8 device runs a layered software architecture.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_end_to_end_user_journey():
    try:
        from agent.llm import LLMClient
        from app import app
        from fastapi.testclient import TestClient
        from rag import chunk_service
        from rag import retriever as rag_retriever
        from services import document_generator
    except ModuleNotFoundError:
        pytest.skip("async app stack / TestClient unavailable")

    # gate on Postgres
    try:
        import asyncio

        from core.database import AsyncSessionLocal, get_engine

        loop = asyncio.new_event_loop()
        admin_creds = None
        try:
            loop.run_until_complete(_db_ok(AsyncSessionLocal))
            # Every endpoint in this journey is auth-protected; seed an
            # admin on the same dedicated loop used for the Postgres check,
            # before that loop is disposed and TestClient claims its own.
            admin_creds = seed_admin_user(loop)
        finally:
            try:
                loop.run_until_complete(get_engine().dispose())
            except Exception:
                pass
            loop.close()
    except Exception as exc:
        if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
            pytest.skip("Postgres unavailable")
        raise

    try:
        with TestClient(app) as client:
            client.headers.update(login_headers_sync(client, *admin_creds))
            monkeypatch_llm = _Monkey(client, LLMClient, "generate", _fake_llm)
            monkeypatch_emb = _Monkey(client, rag_retriever, "embed_text", _fake_embed)
            monkeypatch_gen_emb = _Monkey(client, document_generator, "embed_text", _fake_embed)
            monkeypatch_device_emb = _Monkey(
                client, chunk_service, "get_device_embedding_service",
                lambda: _FakeDeviceEmbeddingService(),
            )

            with monkeypatch_llm, monkeypatch_emb, monkeypatch_gen_emb, monkeypatch_device_emb:
                # 1. Upload a reference document (RAG extraction + embedding)
                docx_bytes = _make_reference_docx()
                ref_resp = client.post(
                    "/rag/reference",
                    files={"file": ("reference.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                )
                assert ref_resp.status_code == 200, ref_resp.text
                ref_json = ref_resp.json()
                reference_id = ref_json["id"]
                assert ref_json["section_count"] >= 1

                # 2. Verify reference + RAG sections stored
                sections_resp = client.get(f"/rag/reference/{reference_id}/sections")
                assert sections_resp.status_code == 200
                sections = sections_resp.json()
                assert len(sections) >= 1
                assert any(s["section_name"] for s in sections)

                # 3. Upload a device document - this both creates the
                # Device (POST /devices/documents always creates a new one,
                # named after the file - there's no "attach to an existing
                # device_id" form field) and, now, automatically generates
                # its sections + chunks + ontology.
                dev_doc_resp = client.post(
                    "/devices/documents",
                    files={
                        "file": (
                            "device.docx",
                            _make_device_docx(),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )
                assert dev_doc_resp.status_code == 201, dev_doc_resp.text
                device_id = dev_doc_resp.json()["id"]

                # 4. Start document generation
                gen_resp = client.post(
                    "/documents/generate",
                    json={
                        "device_id": device_id,
                        "reference_document_id": reference_id,
                    },
                )
                assert gen_resp.status_code == 202, gen_resp.text
                job_id = gen_resp.json()["job_id"]

                # 5. Verify background job lifecycle + wait until complete
                final_status = None
                for _ in range(100):  # up to ~20s
                    status_resp = client.get(f"/documents/{job_id}")
                    assert status_resp.status_code == 200, status_resp.text
                    final_status = status_resp.json()["status"]
                    if final_status in ("completed", "failed"):
                        break
                    time.sleep(0.2)
                assert final_status == "completed", f"job ended as {final_status}"

                # 6. Connect to WebSocket progress and verify hardened payload
                # (the WS route reads its token from a query param, not from
                # TestClient's default header, since browsers can't set custom
                # headers on a WebSocket handshake either)
                ws_token = client.headers["Authorization"].removeprefix("Bearer ")
                with client.websocket_connect(
                    f"/documents/{job_id}/progress?token={ws_token}"
                ) as ws:
                    msg = ws.receive_json()
                    assert msg["job_id"] == job_id
                    assert msg["status"] == "completed"
                    assert "current_section" in msg
                    assert "progress_pct" in msg
                    assert msg["progress_pct"] == 100
                    assert msg["error_message"] is None

                # 8. Download the generated DOCX
                dl_resp = client.get(f"/documents/{job_id}/download")
                assert dl_resp.status_code == 200, dl_resp.text
                content = dl_resp.content
                assert content[:2] == b"PK"  # zip/docx magic

                # 9. Verify it is a valid DOCX (re-open with python-docx)
                verify_doc = DocxDocument(io.BytesIO(content))
                assert len(verify_doc.paragraphs) > 0

    finally:
        cleanup_seeded_user(admin_creds[0])

    # see dispose_engine_sync's docstring: TestClient's portal loop just
    # closed, and it may have left pooled connections bound to that dead
    # loop - dispose again so the next test (any style) starts clean.
    dispose_engine_sync()


class _Monkey:
    """Context-manager monkeypatch bound to the TestClient portal loop.

    starlette's TestClient runs the app in its own anyio portal, so we patch
    on the already-running loop via monkeypatch setattr.
    """

    def __init__(self, client, module_or_obj, attr, fake):
        self._mp = client  # reuse TestClient's monkeypatch helper if present
        self._obj = module_or_obj
        self._attr = attr
        self._fake = fake
        self._real = None

    def __enter__(self):
        self._real = getattr(self._obj, self._attr)
        setattr(self._obj, self._attr, self._fake)
        return self

    def __exit__(self, *exc):
        setattr(self._obj, self._attr, self._real)


async def _db_ok(AsyncSessionLocal):
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT 1"))
