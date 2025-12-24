from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: DefaultDict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, token: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[token].add(websocket)

    def disconnect(self, token: str, websocket: WebSocket) -> None:
        if websocket in self.active_connections.get(token, set()):
            self.active_connections[token].remove(websocket)
        if not self.active_connections[token]:
            self.active_connections.pop(token, None)

    async def broadcast(self, token: str, message: dict) -> None:
        for connection in list(self.active_connections.get(token, set())):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(token, connection)


manager = ConnectionManager()

