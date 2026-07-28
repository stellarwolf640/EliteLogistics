from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

import httpx
from sqlalchemy.exc import OperationalError

from .config import get_settings
from .database import Job, SessionLocal
from .providers import SpanshDumpProvider
from .schemas import TransitRequest
from .engine import plan_transit


def create_job(kind: str) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    with SessionLocal() as session:
        session.add(Job(id=job_id, kind=kind, status="queued", progress=0, created_at=now, updated_at=now))
        session.commit()
    return job_id


def _write_job(job_id: str, change: Callable[[Job], None]) -> None:
    """Make short job-status writes resilient to another SQLite writer."""
    last_error: OperationalError | None = None
    for attempt in range(5):
        try:
            with SessionLocal() as session:
                job = session.get(Job, job_id)
                if job:
                    change(job)
                    job.updated_at = datetime.now(UTC)
                    session.commit()
            return
        except OperationalError as exc:
            last_error = exc
            if "database is locked" not in str(exc).casefold() or attempt == 4:
                raise
            time.sleep(0.1 * (2**attempt))
    if last_error:
        raise last_error


def update_job(job_id: str, progress: float, metadata: dict | None = None) -> None:
    def change(job: Job) -> None:
        job.progress = max(0, min(1, progress))
        if metadata:
            job.result = {**(job.result or {}), **metadata}

    _write_job(job_id, change)


def _run(job_id: str, work: Callable[[], dict]) -> None:
    def mark_running(job: Job) -> None:
        job.status = "running"

    _write_job(job_id, mark_running)
    try:
        result = work()
        def mark_complete(job: Job) -> None:
            job.status = "complete"
            job.progress = 1
            job.result = result

        _write_job(job_id, mark_complete)
    except Exception as exc:
        def mark_failed(job: Job) -> None:
            job.status = "failed"
            job.error = str(exc)

        try:
            _write_job(job_id, mark_failed)
        except Exception:
            # The worker must not emit a second unhandled traceback if SQLite
            # itself is unavailable while recording the original failure.
            return


def start_transit_job(request: TransitRequest) -> str:
    job_id = create_job("transit")

    def work() -> dict:
        with SessionLocal() as session:
            return plan_transit(session, request).model_dump(mode="json")

    threading.Thread(target=_run, args=(job_id, work), daemon=True).start()
    return job_id


def start_import_job(path: Path, download: bool = False) -> str:
    job_id = create_job("spansh_import")

    def work() -> dict:
        if download:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".part")
            url = "https://downloads.spansh.co.uk/galaxy_stations.json.gz"
            existing = temporary.stat().st_size if temporary.exists() else 0
            headers = {"Range": f"bytes={existing}-"} if existing else {}
            with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=None) as response:
                response.raise_for_status()
                resumed = existing > 0 and response.status_code == 206
                if not resumed:
                    existing = 0
                content_range = response.headers.get("content-range", "")
                total = int(content_range.rsplit("/", 1)[-1]) if "/" in content_range else (
                    existing + int(response.headers.get("content-length", 0) or 0)
                )
                received = existing
                started = time.monotonic()
                last_report = 0.0
                with temporary.open("ab" if resumed else "wb") as target:
                    for chunk in response.iter_bytes(1024 * 1024):
                        target.write(chunk)
                        received += len(chunk)
                        elapsed = max(0.001, time.monotonic() - started)
                        if elapsed - last_report >= 1 or (total and received >= total):
                            transferred = received - existing
                            speed = transferred / elapsed
                            eta = (total - received) / speed if total and speed else None
                            update_job(
                                job_id,
                                min(0.35, received / total * 0.35) if total else 0.05,
                                {
                                    "phase": "Downloading",
                                    "downloaded_bytes": received,
                                    "total_bytes": total,
                                    "speed_bps": round(speed),
                                    "eta_seconds": round(eta) if eta is not None else None,
                                },
                            )
                            last_report = elapsed
            temporary.replace(path)
        update_job(job_id, 0.4, {"phase": "Indexing"})
        with SessionLocal() as session:
            counts = SpanshDumpProvider(session).import_file(path)
            update_job(job_id, 0.95)
            return {"counts": counts, "path": str(path)}

    threading.Thread(target=_run, args=(job_id, work), daemon=True).start()
    return job_id
