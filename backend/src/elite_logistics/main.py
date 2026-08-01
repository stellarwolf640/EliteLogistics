from __future__ import annotations

import os
import webbrowser
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles

from .api import router
from .database import init_database
from .elite_monitor import elite_monitor
from .events import event_bus, state_snapshot
from .input_bridge import input_bridge
from .speech_input import speech_recognizer
from .config import resource_path
from .version import APP_VERSION


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return FileResponse(Path(self.directory) / "index.html")
        if response.status_code == 404:
            return FileResponse(Path(self.directory) / "index.html")
        return response


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_database()
        elite_monitor.start()
        input_bridge.start()
        try:
            yield
        finally:
            speech_recognizer.cancel()
            input_bridge.stop()
            elite_monitor.stop()

    app = FastAPI(title="ION API", version=APP_VERSION, lifespan=lifespan)
    app.include_router(router)
    @app.websocket("/api/events")
    async def events_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        requested = int(websocket.query_params.get("last_sequence", "0") or 0)
        subscriber_id, queue = event_bus.subscribe()
        try:
            replay = event_bus.replay_after(requested)
            if replay is None or requested == 0:
                await websocket.send_json(
                    {
                        "sequence": event_bus.sequence,
                        "type": "state.snapshot",
                        "timestamp": datetime.now(UTC).isoformat(),
                        "payload": state_snapshot(),
                    }
                )
            else:
                for event in replay:
                    await websocket.send_json(event)
            while True:
                await websocket.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            event_bus.unsubscribe(subscriber_id)

    frontend_dist = resource_path("frontend", "dist")
    if frontend_dist.exists():
        app.mount("/", SpaStaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


app = create_app()


def run() -> None:
    if os.getenv("ELITE_LOGISTICS_OPEN_BROWSER", "1") == "1":
        import threading

        threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8765")).start()
    uvicorn.run("elite_logistics.main:app", host="127.0.0.1", port=8765)


if __name__ == "__main__":
    run()
