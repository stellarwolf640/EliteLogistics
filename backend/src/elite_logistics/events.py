from __future__ import annotations

import asyncio
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any


class EventBus:
    """Thread-safe process-local event publisher with bounded replay."""

    def __init__(self, capacity: int = 500):
        self._capacity = capacity
        self._events: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._sequence = 0
        self._lock = threading.Lock()
        self._subscribers: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = {}
        self._subscriber_id = 0

    def publish(self, event_type: str, payload: Any) -> dict[str, Any]:
        with self._lock:
            self._sequence += 1
            event = {
                "sequence": self._sequence,
                "type": event_type,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload": payload,
            }
            self._events.append(event)
            subscribers = list(self._subscribers.values())
        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(self._offer, queue, event)
            except RuntimeError:
                pass
        return event

    @staticmethod
    def _offer(queue: asyncio.Queue, event: dict[str, Any]) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(event)

    def subscribe(self) -> tuple[int, asyncio.Queue]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        with self._lock:
            self._subscriber_id += 1
            subscriber_id = self._subscriber_id
            self._subscribers[subscriber_id] = (loop, queue)
        return subscriber_id, queue

    def unsubscribe(self, subscriber_id: int) -> None:
        with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def replay_after(self, sequence: int) -> list[dict[str, Any]] | None:
        with self._lock:
            if not self._events:
                return []
            oldest = self._events[0]["sequence"]
            if sequence and sequence < oldest - 1:
                return None
            return [event for event in self._events if event["sequence"] > sequence]

    @property
    def sequence(self) -> int:
        with self._lock:
            return self._sequence


event_bus = EventBus()


def state_snapshot() -> dict[str, Any]:
    """Small transport snapshot; REST remains authoritative for full state."""
    from sqlalchemy import func, select

    from .database import ActiveOperation, Job, MarketObservation, SessionLocal

    with SessionLocal() as session:
        operation = session.get(ActiveOperation, 1)
        jobs = session.execute(
            select(Job.id, Job.kind, Job.status, Job.progress)
            .where(Job.status.in_(("queued", "running")))
        ).all()
        return {
            "active_operation": (
                {
                    "operation_type": operation.operation_type,
                    "title": operation.title,
                    "manual_progress": operation.manual_progress,
                    "status": operation.status,
                    "updated_at": operation.updated_at.isoformat(),
                }
                if operation
                else None
            ),
            "active_jobs": [
                {"id": row.id, "kind": row.kind, "status": row.status, "progress": row.progress}
                for row in jobs
            ],
            "market_observations": session.scalar(
                select(func.count()).select_from(MarketObservation)
            )
            or 0,
        }
