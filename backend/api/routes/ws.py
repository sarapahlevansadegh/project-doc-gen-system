"""WebSocket progress streaming for generation jobs."""
from __future__ import annotations

import asyncio
import json

from api.deps import get_db
from core.security import decode_token
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from services import generation_service
from sqlalchemy.ext.asyncio import AsyncSession

ws_router = APIRouter()


@ws_router.websocket("/documents/{job_id}/progress")
async def document_progress(
    websocket: WebSocket,
    job_id: str,
    token: str | None = Query(default=None),
):
    protocol = None
    if token is None:
        for candidate in websocket.headers.get("sec-websocket-protocol", "").split(","):
            candidate = candidate.strip()
            if candidate.startswith("docgen."):
                token = candidate.removeprefix("docgen.")
                protocol = candidate
                break

    if token is None:
        await websocket.close(code=1008)
        return

    await websocket.accept(subprotocol=protocol)
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None or payload.get("type") != "access":
            await websocket.send_text(json.dumps({"detail": "Invalid token"}))
            await websocket.close()
            return
    except Exception:
        await websocket.send_text(json.dumps({"detail": "Invalid token"}))
        await websocket.close()
        return

    db_gen = get_db()
    db: AsyncSession = await db_gen.__anext__()
    try:
        last_seen = None
        while True:
            job = await generation_service.get_job(db, job_id)
            if job is not None:
                # The WS session is reused for the whole connection and is
                # created with expire_on_commit=False, so the cached job
                # object would otherwise never reflect the generation task's
                # DB commits. Force a fresh read from the database each poll.
                await db.refresh(job)
            if job is None:
                await websocket.send_text(
                    json.dumps(
                        {
                            "job_id": job_id,
                            "status": "not_found",
                            "current_section": None,
                            "progress_pct": 0,
                            "error_message": None,
                        }
                    )
                )
                break

            event = {
                "job_id": str(job.id),
                "status": job.status,
                "current_section": job.current_section,
                "progress_pct": job.progress_pct,
                "error_message": job.error_message if job.status == "failed" else None,
            }
            # emit only on change to avoid spamming
            if event != last_seen:
                await websocket.send_text(json.dumps(event))
                last_seen = event

            if job.status in ("completed", "failed"):
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await db_gen.aclose()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
