import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import socketio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from infinex.control_plane.api import router
from infinex.control_plane.db import init_db
from infinex.control_plane.logging import RequestLoggingMiddleware, configure_logging
from infinex.control_plane.maintenance import worker_status_loop
from infinex.control_plane.realtime import sio
from infinex.control_plane.settings import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    settings.artifact_dir.mkdir(parents=True, exist_ok=True)
    settings.worker_data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    status_task = asyncio.create_task(worker_status_loop())
    try:
        yield
    finally:
        status_task.cancel()
        with suppress(asyncio.CancelledError):
            await status_task


def create_fastapi_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(title=settings.app_name, lifespan=lifespan)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.include_router(router)

    web_dist = settings.web_dist_dir
    assets_dir = web_dist / "assets"
    if assets_dir.is_dir():
        application.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @application.get("/", include_in_schema=False, response_model=None)
    def index() -> Any:
        index_path = web_dist / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        return {
            "name": settings.app_name,
            "docs": "/docs",
            "health": "/api/health",
        }

    @application.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = web_dist / path
        if candidate.is_file() and Path(candidate).is_relative_to(web_dist):
            return FileResponse(candidate)
        index_path = web_dist / "index.html"
        if index_path.is_file():
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Web console has not been built")

    return application


fastapi_app = create_fastapi_app()
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path="socket.io")
