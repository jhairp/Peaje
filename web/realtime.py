"""
Motor de Eventos en Tiempo Real (Sección 4.3)
Soporta simultáneamente WebSockets (/ws/eventos) y Server-Sent Events (/api/v1/eventos/stream)
para actualizar el panel web al instante con cada vehículo registrado, recaudación y alerta.
"""
import asyncio
import json
from typing import Any, Dict, List, Set
from fastapi import WebSocket


class GestorTiempoReal:
    def __init__(self):
        self.conexiones_ws: Set[WebSocket] = set()
        self.colas_sse: List[asyncio.Queue] = []

    async def conectar_ws(self, ws: WebSocket):
        await ws.accept()
        self.conexiones_ws.add(ws)

    def desconectar_ws(self, ws: WebSocket):
        self.conexiones_ws.discard(ws)

    def suscribir_sse(self) -> asyncio.Queue:
        cola: asyncio.Queue = asyncio.Queue(maxsize=100)
        self.colas_sse.append(cola)
        return cola

    def desuscribir_sse(self, cola: asyncio.Queue):
        if cola in self.colas_sse:
            self.colas_sse.remove(cola)

    async def emitir_evento(self, tipo: str, datos: Dict[str, Any]):
        mensaje = json.dumps({"tipo": tipo, "datos": datos}, ensure_ascii=False, default=str)

        # 1. Enviar a todos los clientes WebSocket conectados
        ws_caidos = []
        for ws in list(self.conexiones_ws):
            try:
                await ws.send_text(mensaje)
            except Exception:
                ws_caidos.append(ws)
        for ws in ws_caidos:
            self.desconectar_ws(ws)

        # 2. Enviar a todos los clientes SSE suscritos
        for cola in list(self.colas_sse):
            try:
                cola.put_nowait(mensaje)
            except asyncio.QueueFull:
                pass


gestor_rt = GestorTiempoReal()
