"""End-to-end user journey integration test (Milestone 5.2).

Exercises the full API flow with no real LLM or embedding model:
  1. Create a Device
  2. Upload a reference .docx (RAG extraction + embedding stored)
  3. Verify reference + RAG sections persisted
  4. Start document generation
  5. Verify background job lifecycle
  6. Connect to WebSocket progress and verify payload
  7. Wait until generation completes
  8. Download the generated DOCX
  9. Verify the file exists and is a valid .docx

The real LLM and embedding calls are replaced with deterministic
implementations via monkeypatch (same spirit as the mocked-LLM tests in
test_agent.py) so the journey runs hermetically against Postgres.
"""
from __future__ import annotations

import io
import time

import pytest
from docx import Document as DocxDocument

EMBED_DIM = 384


def _fake_llm(self, prompt: str, max_tokens: int, temperature: float) -> str:
    lower = prompt.lower()
    if "lcd module" in lower:
        return "LCD Module: 7-inch touch LCD showing status and alerts."
    if "serial communication" in lower:
        return "Serial Communication: RS-232 at 115200 baud."
    return "Generated section content for the requested topic."


async def _fake_embed(text: str) -> list[float]:
    # deterministic fixed-dimension vector (matches Vector(384) column)
    return [0.0] * EMBED_DIM


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


def test_end_to_end_user_journey():
    try:
        from agent.llm import LLMClient
        from app import app
        from fastapi.testclient import TestClient
        from rag import retriever as rag_retriever
    except ModuleNotFoundError:
        pytest.skip("async app stack / TestClient unavailable")

    # gate on Postgres
    try:
        import asyncio

        from core.database import AsyncSessionLocal, get_engine

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_db_ok(AsyncSessionLocal))
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

    with TestClient(app) as client:
        monkeypatch_llm = _Monkey(client, LLMClient, "generate", _fake_llm)
        monkeypatch_emb = _Monkey(client, rag_retriever, "embed_text", _fake_embed)

        with monkeypatch_llm, monkeypatch_emb:
            # 1. Create a Device
            dev_resp = client.post(
                "/devices",
                json={
                    "name": "VL8",
                    "model": "VL8",
                    "document_code": "15799",
                    "safety_class": "B",
                    "driver_version": "01",
                    "gui_version": "7.0.0.1",
                },
            )
            assert dev_resp.status_code == 201, dev_resp.text
            device_id = dev_resp.json()["id"]

            # 2. Upload a reference document (RAG extraction + embedding)
            docx_bytes = _make_reference_docx()
            ref_resp = client.post(
                "/rag/reference",
                files={"file": ("reference.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
            assert ref_resp.status_code == 200, ref_resp.text
            ref_json = ref_resp.json()
            reference_id = ref_json["id"]
            assert ref_json["section_count"] >= 1

            # 3. Verify reference + RAG sections stored
            sections_resp = client.get(f"/rag/reference/{reference_id}/sections")
            assert sections_resp.status_code == 200
            sections = sections_resp.json()
            assert len(sections) >= 1
            assert any(s["section_name"] for s in sections)

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

            # 5 + 7. Verify background job lifecycle + wait until complete
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
            with client.websocket_connect(f"/documents/{job_id}/progress") as ws:
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
