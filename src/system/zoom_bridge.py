"""Chrome 확장이 보내는 브라우저 배율을 백그라운드에서 수신한다.

확장은 tabs 권한만 사용하며 페이지에 content script 를 주입하지 않는다.
이 모듈은 별도 스레드에서 WebSocket 서버를 돌리고, 최신 값을 메모리에 둔다.

S3 검증(2026-08-26): 배율 변경이 62~234ms 내 반영됨.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field

import websockets

DEFAULT_PORT = 8777


@dataclass
class ZoomState:
    """확장에서 마지막으로 수신한 배율 상태."""
    zoom: int | None = None
    url: str = ""
    updated_at: float = 0.0
    connected: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def update(self, zoom: int, url: str) -> None:
        with self._lock:
            self.zoom, self.url, self.updated_at = zoom, url, time.time()

    def snapshot(self) -> tuple[int | None, str, bool]:
        """(배율, url, 최근 수신 여부)를 반환한다. 5초 이상 무소식이면 끊긴 것."""
        with self._lock:
            fresh = self.updated_at > 0 and (time.time() - self.updated_at) < 5
            return (self.zoom if fresh else None), self.url, fresh


state = ZoomState()


async def _handler(ws) -> None:
    """확장 연결 하나를 처리한다."""
    state.connected = True
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            zoom = msg.get("zoom")
            if isinstance(zoom, int):
                state.update(zoom, msg.get("url") or "")
    except Exception:
        pass
    finally:
        state.connected = False


def _run(port: int) -> None:
    """이벤트 루프를 새로 만들어 서버를 돌린다."""
    async def serve() -> None:
        async with websockets.serve(_handler, "127.0.0.1", port):
            await asyncio.Future()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(serve())
    except Exception:
        pass


def start(port: int = DEFAULT_PORT) -> threading.Thread:
    """데몬 스레드로 브리지를 시작한다. 중복 호출은 무해하다."""
    for t in threading.enumerate():
        if t.name == "zoom-bridge":
            return t
    t = threading.Thread(target=_run, args=(port,), name="zoom-bridge",
                         daemon=True)
    t.start()
    return t
