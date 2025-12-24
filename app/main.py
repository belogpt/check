from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import receipts as receipts_router
from app.core.config import get_settings
from app.core.websocket_manager import manager
from app.db import get_session
from app.models import Receipt, ReceiptStatus
from app.schemas import HealthResponse, ReceiptRoomResponse


settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
media_root = Path(settings.media_root)
media_root.mkdir(parents=True, exist_ok=True)

app = FastAPI(title=settings.app_name)

if settings.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin) for origin in settings.allowed_origins],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )


app.include_router(receipts_router.router)

static_path = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=static_path), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/review/{receipt_id}", response_class=HTMLResponse)
async def review_page(request: Request, receipt_id: str, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
    from uuid import UUID

    try:
        receipt_uuid = UUID(receipt_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Receipt not found")
    receipt = await session.get(Receipt, receipt_uuid)
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return templates.TemplateResponse("review.html", {"request": request, "receipt_id": receipt_id})


@app.get("/r/{token}", name="room_page", response_class=HTMLResponse)
async def room_page(request: Request, token: str, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
    receipt_result = await session.execute(select(Receipt).where(Receipt.token == token))
    receipt = receipt_result.scalar_one_or_none()
    if not receipt:
        raise HTTPException(status_code=404, detail="Room not found")
    return templates.TemplateResponse("room.html", {"request": request, "token": token})


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.websocket("/ws/rooms/{token}")
async def websocket_endpoint(token: str, websocket: WebSocket, session: AsyncSession = Depends(get_session)) -> None:
    await manager.connect(token, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(token, websocket)
