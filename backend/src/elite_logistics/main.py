from __future__ import annotations

import os
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from starlette.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles

from .api import router
from .database import init_database


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
        yield

    app = FastAPI(title="Elite Logistics API", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    frontend_dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
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
