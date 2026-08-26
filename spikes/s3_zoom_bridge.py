"""S3 - Chrome 확장에서 보내는 줌 배율을 로컬에서 수신 검증.

브라우저 줌은 외부 프로세스에서 읽을 수 없다. Chrome 확장이 tabs 권한으로
chrome.tabs.getZoom 을 호출해 WebSocket 으로 보내주는 구조를 검증한다.
확장은 페이지에 content script 를 주입하지 않는다.

실행 순서:
  1. 이 스크립트를 먼저 실행 (서버 대기)
  2. chrome://extensions -> 개발자 모드 -> 압축해제된 확장 프로그램 로드
     -> spikes/extension 폴더 선택
  3. 아무 탭에서 Ctrl + '+' / Ctrl + '-' 로 배율 변경

통과 기준: 배율 변경이 0.5초 내 콘솔에 반영
"""
from __future__ import annotations

import asyncio
import json
import time

import websockets

PORT = 8777
last_seen = {"zoom": None, "at": 0.0}


async def handler(ws):
    """확장이 보낸 줌 값을 수신해 변경 시에만 출력한다."""
    print(f"  확장 연결됨: {ws.remote_address}")
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print(f"  파싱 실패: {raw[:60]}")
                continue

            zoom = msg.get("zoom")
            if zoom is None:
                continue

            if zoom != last_seen["zoom"]:
                now = time.monotonic()
                delta = (now - last_seen["at"]) * 1000 if last_seen["at"] else 0
                host = (msg.get("url") or "")[:48]
                lag = f"  (직전 변경 후 {delta:.0f}ms)" if delta else ""
                print(f"  배율 {zoom:>4}%   {host}{lag}")
                last_seen.update(zoom=zoom, at=now)
    except websockets.ConnectionClosed:
        print("  확장 연결 종료")


async def main():
    print("=" * 56)
    print("S3  Chrome 확장 줌 브리지 검증")
    print("=" * 56)
    print(f"\n  ws://127.0.0.1:{PORT} 에서 대기 중")
    print("  chrome://extensions 에서 spikes/extension 폴더를 로드하세요.")
    print("  종료: Ctrl+C\n")

    async with websockets.serve(handler, "127.0.0.1", PORT):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n종료")
