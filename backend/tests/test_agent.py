"""Tests for the AI agent workflow (Milestone 3).

Pure-logic tests (workflow orchestration, dynamic section discovery, mocked
LLM, job status transitions, failure handling) run without a database by using
a small in-memory fake async session.

DB-backed API tests auto-skip when Postgres is unavailable (or when the async
test plugin / app stack is not importable).
"""
from __future__ import annotations

import uuid

import pytest

# ---------- helpers ----------


def _fake_llm(prompt: str, max_tokens: int, temperature: float) -> str:
    # Echo a deterministic "generated" section based on the prompt.
    lower = prompt.lower()
    if "lcd module" in lower:
        return "LCD Module: The new device presents a 7-inch touch LCD showing status and alerts."
    if "serial communication" in lower:
        return "Serial Communication: RS-232 at 115200 baud, little-endian, XOR checksum."
    return "Generated section content for the requested topic."


class _FakeDevice:
    def __init__(self):
        self.name = "VL8"
        self.model = "VL8"
        self.document_code = "15799"
        self.safety_class = "B"
        self.driver_version = "01"
        self.gui_version = "7.0.0.1"


class _FakeRow:
    """Minimal stand-in for a DocumentTemplate row."""

    def __init__(self, name, content, order):
        self.section_name = name
        self.content = content
        self.section_order = order


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeExecute:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return self.rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return [(r.content, r.section_name) for r in self.rows]


class _FakeSession:
    """In-memory async session stub for workflow tests.

    Selects sensible in-memory data depending on the entity being queried:
      - Device            -> a single fake device
      - DeviceSpec/Alarm/Command -> empty (no extras)
      - DocumentTemplate  -> reference sections (dynamic discovery)
      - raw text() RAG SQL -> empty context
    """

    def __init__(self, sections):
        self._sections = sections
        self._device = _FakeDevice()
        self.committed = []
        self.ref_doc_id = str(uuid.uuid4())

    async def execute(self, stmt, params=None):
        # Raw text RAG query -> no similar sections.
        if getattr(stmt, "text", None) is not None:
            return _FakeExecute([])

        # Resolve the target table name from the select's columns.
        # `select(Entity)` yields the table object; `select(Entity.col)` yields
        # a Column whose `.table` is the table. Support both shapes.
        table_name = None
        raw = getattr(stmt, "_raw_columns", None)
        if raw:
            first = raw[0]
            if getattr(first, "columns", None) is not None:
                table_name = getattr(first, "name", None)
            else:
                table = getattr(first, "table", None)
                if table is not None:
                    table_name = getattr(table, "name", None)


        if table_name == "devices":
            return _ScalarResult([self._device])
        if table_name in ("device_specs", "device_alarms", "serial_commands"):
            return _ScalarResult([])
        if table_name == "document_templates":
            return _ScalarResult(self._sections)
        # Fallback: behave like reference discovery.
        return _ScalarResult(self._sections)

    async def commit(self):
        self.committed.append(True)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    async def close(self):
        self.closed = True


def _make_sections():
    return [
        _FakeRow("1.1 LCD Module", "Reference LCD content about touch display.", 1),
        _FakeRow("2. Serial Communication Architecture", "Reference RS-232 details.", 2),
        _FakeRow("7. Software Specifications", "Driver/Qt specs table.", 3),
    ]


@pytest.fixture(autouse=True)
def _stub_rag(monkeypatch):
    """Avoid loading the heavy embedding model in pure-logic tests.

    The mocked-LLM workflow tests only exercise orchestration + section
    generation; RAG retrieval is stubbed to return no extra context."""
    from rag import retriever

    async def _fake_retrieve(db, query, k=3, reference_doc_id=None):
        return []

    monkeypatch.setattr(retriever, "retrieve_similar_sections", _fake_retrieve)


# ---------- tests ----------


def test_workflow_discovers_sections_dynamically():
    session = _FakeSession(_make_sections())

    import asyncio

    async def _run():
        from agent.workflow import discover_reference_sections

        secs = await discover_reference_sections(session, session.ref_doc_id)
        return [s.section_name for s in secs]

    names = asyncio.run(_run())
    # no hardcoded names â€” derived from the (fake) reference rows
    assert names == [
        "1.1 LCD Module",
        "2. Serial Communication Architecture",
        "7. Software Specifications",
    ]


def test_workflow_generates_each_section_with_mocked_llm():
    session = _FakeSession(_make_sections())

    events = []

    async def _progress(event):
        events.append(event)

    import asyncio

    from agent.llm import LLMClient
    from agent.workflow import generate_document

    async def _run():
        return await generate_document(
            db=session,
            device_id="00000000-0000-0000-0000-000000000001",
            reference_doc_id=session.ref_doc_id,
            llm_client=LLMClient(generate_fn=_fake_llm),
            progress_callback=_progress,
        )

    result = asyncio.run(_run())
    sections = result["sections"]
    assert set(sections.keys()) == {
        "1.1 LCD Module",
        "2. Serial Communication Architecture",
        "7. Software Specifications",
    }
    assert "7-inch touch LCD" in sections["1.1 LCD Module"]
    assert "RS-232" in sections["2. Serial Communication Architecture"]
    # progress events streamed and end at 100%
    assert events[-1]["progress"] == 100
    assert events[0]["status"] == "processing"
    # device data was loaded from the fake session
    assert result["device_data"]["name"] == "VL8"


def test_job_status_transitions_with_mocked_llm():
    """Exercise generation_service.run_generation status flow in-memory."""

    import asyncio

    from services import generation_service

    class _FakeJob:

        id = uuid.uuid4()
        status = "pending"
        progress_pct = 0
        current_section = None
        result_sections = None
        error_message = None
        completed_at = None
        device_id = uuid.uuid4()
        reference_doc_id = uuid.uuid4()

    job = _FakeJob()
    session = _FakeSession(_make_sections())

    async def _run():
        await generation_service.run_generation(
            job_id="00000000-0000-0000-0000-000000000000",
            generate_fn=_fake_llm,
            db_factory=lambda: session,
            job=job,
        )

    asyncio.run(_run())
    assert job.status == "completed"
    assert job.progress_pct == 100
    assert job.result_sections is not None
    assert "1.1 LCD Module" in job.result_sections


def test_failure_handling_sets_failed_status():
    def _boom(prompt, max_tokens, temperature):
        raise RuntimeError("LLM outage")

    import asyncio

    from services import generation_service

    class _FakeJob:
        id = uuid.uuid4()
        status = "pending"
        progress_pct = 0
        current_section = None
        result_sections = None
        error_message = None
        completed_at = None
        device_id = uuid.uuid4()
        reference_doc_id = uuid.uuid4()

    job = _FakeJob()
    session = _FakeSession(_make_sections())

    async def _run():
        await generation_service.run_generation(
            job_id="00000000-0000-0000-0000-000000000000",
            generate_fn=_boom,
            db_factory=lambda: session,
            job=job,
        )

    with pytest.raises(RuntimeError):
        asyncio.run(_run())
    assert job.status == "failed"
    assert "LLM outage" in job.error_message


# ---------- DB-gated API tests ----------


async def _db_available() -> bool:
    try:
        from core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            from sqlalchemy import text

            await db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _run_endpoint_tests():
    """Only executed when the async stack is importable AND Postgres is up."""
    import tempfile
    from pathlib import Path

    from app import app
    from core.database import AsyncSessionLocal
    from httpx import ASGITransport, AsyncClient
    from models.device import Device
    from models.document import GeneratedDocument

    if not await _db_available():
        pytest.skip("Postgres unavailable")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/documents/generate",
            json={
                "device_id": str(uuid.uuid4()),
                "reference_document_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code in (202, 404)  # 404 if device/ref missing
        if resp.status_code == 202:
            assert "job_id" in resp.json()

        # --- smart generation (Milestone 6.3) ---
        from models.template import ReferenceDocument

        # seed an active reference + a device, then generate without ref id
        active_ref_id = str(uuid.uuid4())
        device_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(
                ReferenceDocument(
                    id=uuid.UUID(active_ref_id),
                    filename="active_ref.docx",
                    template_name="active_ref",
                    is_active=True,
                    section_count=1,
                    version=1,
                    embedding_model="test",
                    embedding_dimension=384,
                )
            )
            db.add(
                Device(
                    id=uuid.UUID(device_id),
                    name="SmartDevice",
                    model="VL8",
                )
            )
            await db.commit()

        smart = await client.post(
            "/documents/generate",
            json={"device_id": device_id},
        )
        assert smart.status_code == 202, smart.text
        assert "job_id" in smart.json()

        # deactivate all references -> generate without ref id should 404
        async with AsyncSessionLocal() as db:
            ref = await db.get(ReferenceDocument, uuid.UUID(active_ref_id))
            if ref is not None:
                ref.is_active = False
                await db.commit()

        no_active = await client.post(
            "/documents/generate",
            json={"device_id": device_id},
        )
        assert no_active.status_code == 404, no_active.text

        resp = await client.get(f"/documents/{uuid.uuid4()}")
        assert resp.status_code == 404

        # --- download endpoint (Milestone 4.3) ---
        missing = await client.get(f"/documents/{uuid.uuid4()}/download")
        assert missing.status_code == 404

        # seed a valid device so FK constraints hold, then a completed job
        # pointing at a real temp file
        tmp = Path(tempfile.mkdtemp()) / "sample.docx"
        tmp.write_bytes(b"PK\x03\x04 fake docx content")

        device_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(
                Device(
                    id=uuid.UUID(device_id),
                    name="TestDevice",
                    model="VL8",
                )
            )
            await db.commit()

        job_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(
                GeneratedDocument(
                    id=uuid.UUID(job_id),
                    device_id=uuid.UUID(device_id),
                    reference_doc_id=None,
                    status="completed",
                    progress_pct=100,
                    file_path=str(tmp),
                    version=1,
                )
            )
            await db.commit()

        ok = await client.get(f"/documents/{job_id}/download")
        assert ok.status_code == 200
        assert ok.content == b"PK\x03\x04 fake docx content"

        # not-completed job -> error (no FileResponse)
        pending_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(
                GeneratedDocument(
                    id=uuid.UUID(pending_id),
                    device_id=uuid.UUID(device_id),
                    reference_doc_id=None,
                    status="processing",
                    progress_pct=10,
                    file_path=str(tmp),
                    version=1,
                )
            )
            await db.commit()

        pending = await client.get(f"/documents/{pending_id}/download")
        assert pending.status_code == 409

        # completed but file missing -> 404
        missing_file_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(
                GeneratedDocument(
                    id=uuid.UUID(missing_file_id),
                    device_id=uuid.UUID(device_id),
                    reference_doc_id=None,
                    status="completed",
                    progress_pct=100,
                    file_path=str(Path(tempfile.mkdtemp()) / "gone.docx"),
                    version=1,
                )
            )
            await db.commit()

        gone = await client.get(f"/documents/{missing_file_id}/download")
        assert gone.status_code == 404

        # --- document version history (Milestone 7.1) ---
        hist_device_id = str(uuid.uuid4())
        hist_ref_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(
                Device(id=uuid.UUID(hist_device_id), name="HistDevice", model="VL8")
            )
            db.add(
                ReferenceDocument(
                    id=uuid.UUID(hist_ref_id),
                    filename="hist_ref.docx",
                    template_name="hist_ref",
                    is_active=True,
                    section_count=1,
                    version=1,
                    embedding_model="test",
                    embedding_dimension=384,
                )
            )
            await db.commit()

        r1 = await client.post(
            "/documents/generate",
            json={"device_id": hist_device_id},
        )
        assert r1.status_code == 202, r1.text

        r2 = await client.post(
            "/documents/generate",
            json={"device_id": hist_device_id},
        )
        assert r2.status_code == 202, r2.text

        hist = await client.get(f"/documents/history/{hist_device_id}")
        assert hist.status_code == 200, hist.text
        items = hist.json()
        assert len(items) == 2
        versions = [item["version"] for item in items]
        assert sorted(versions) == [1, 2]
        assert items[0]["version"] == 2
        assert items[0]["status"] in ("pending", "processing", "completed", "failed")
        assert items[1]["version"] == 1

        assert client.get(f"/documents/history/{uuid.uuid4()}").status_code == 404


async def _seed_document(device_id, job_id, status, progress, section=None,
                         error=None, file_path=None, version=1):
    from core.database import AsyncSessionLocal
    from models.document import GeneratedDocument

    async with AsyncSessionLocal() as db:
        db.add(
            GeneratedDocument(
                id=uuid.UUID(job_id),
                device_id=uuid.UUID(device_id),
                reference_doc_id=None,
                status=status,
                progress_pct=progress,
                current_section=section,
                error_message=error,
                file_path=file_path,
                version=version,
            )
        )
        await db.commit()


def test_websocket_progress():
    """WebSocket progress endpoint emits hardened payloads, gated on Postgres."""
    import asyncio

    try:
        from app import app
        from core.database import AsyncSessionLocal, get_engine
        from fastapi.testclient import TestClient
        from models.device import Device
    except ModuleNotFoundError:
        pytest.skip("async app stack / TestClient unavailable")

    device_id = str(uuid.uuid4())
    not_found_id = str(uuid.uuid4())
    failed_id = str(uuid.uuid4())
    pending_id = str(uuid.uuid4())
    completed_id = str(uuid.uuid4())

    # gate + seed on a dedicated loop (TestClient runs its own loop for WS)
    loop = asyncio.new_event_loop()
    try:
        try:
            loop.run_until_complete(_db_available())
        except Exception as exc:
            if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
                pytest.skip("Postgres unavailable")
            raise

        async def _seed():
            async with AsyncSessionLocal() as db:
                db.add(
                    Device(id=uuid.UUID(device_id), name="TestDevice", model="VL8")
                )
                await db.commit()
            await _seed_document(device_id, failed_id, "failed", 50,
                                 section="LCD Module", error="LLM outage")
            await _seed_document(device_id, pending_id, "processing", 10)
            await _seed_document(device_id, completed_id, "completed", 100)

        try:
            loop.run_until_complete(_seed())
        except Exception as exc:
            if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
                pytest.skip("Postgres unavailable")
            raise
    finally:
        # release engine so TestClient's own loop can rebind it
        try:
            loop.run_until_complete(get_engine().dispose())
        except Exception:
            pass
        loop.close()

    with TestClient(app) as client:
        # not_found job -> single message with status not_found, then closed
        with client.websocket_connect(
            f"/documents/{not_found_id}/progress"
        ) as ws:
            msg = ws.receive_json()
            assert msg["status"] == "not_found"
            assert msg["job_id"] == not_found_id
            assert msg["current_section"] is None
            assert msg["progress_pct"] == 0
            assert msg["error_message"] is None

        # failed job -> error_message present, then closed
        with client.websocket_connect(
            f"/documents/{failed_id}/progress"
        ) as ws:
            msg = ws.receive_json()
            assert msg["job_id"] == failed_id
            assert msg["status"] == "failed"
            assert msg["current_section"] == "LCD Module"
            assert msg["progress_pct"] == 50
            assert msg["error_message"] == "LLM outage"

        # processing job -> emits current state, then closed
        with client.websocket_connect(
            f"/documents/{pending_id}/progress"
        ) as ws:
            msg = ws.receive_json()
            assert msg["job_id"] == pending_id
            assert msg["status"] == "processing"
            assert msg["progress_pct"] == 10
            assert msg["error_message"] is None

        # completed job -> emits final state, then closed
        with client.websocket_connect(
            f"/documents/{completed_id}/progress"
        ) as ws:
            msg = ws.receive_json()
            assert msg["job_id"] == completed_id
            assert msg["status"] == "completed"
            assert msg["progress_pct"] == 100


def test_generate_endpoint_and_status():
    try:
        import asyncio

        asyncio.run(_run_endpoint_tests())
    except ModuleNotFoundError:
        pytest.skip("async app stack / pytest-asyncio unavailable")
    except Exception as exc:
        # Any other import/runtime error means the DB-backed path can't run here.
        if "SELECT 1" in str(exc) or "connect" in str(exc).lower():
            pytest.skip("Postgres unavailable")
        raise

