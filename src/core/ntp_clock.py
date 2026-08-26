"""NTP 기준 시각으로 서버시각 추정치를 교차검증한다.

HTTP Date 동기화 실패 시의 폴백이자, 성공 시에는 두 값의 차이를 표시해
사용자가 이상을 감지할 수 있게 하는 용도다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import ntplib

KST = timezone(timedelta(hours=9))
SERVERS = ("kr.pool.ntp.org", "time.google.com", "pool.ntp.org")


@dataclass(frozen=True)
class NtpSync:
    """NTP 동기화 결과."""
    offset_sec: float
    server: str
    delay_ms: float


def sync(servers: tuple[str, ...] = SERVERS, timeout: float = 3.0) -> NtpSync:
    """NTP 서버에서 시각 오프셋을 가져온다.

    Raises:
        RuntimeError: 모든 서버 조회에 실패한 경우.
    """
    client = ntplib.NTPClient()
    last: Exception | None = None

    for host in servers:
        try:
            r = client.request(host, version=3, timeout=timeout)
            return NtpSync(offset_sec=r.offset, server=host,
                           delay_ms=r.delay * 1000)
        except Exception as exc:
            last = exc
            continue

    raise RuntimeError(f"NTP 동기화 실패 ({type(last).__name__})")


def now(s: NtpSync) -> datetime:
    """NTP 보정 현재 KST 시각."""
    return datetime.fromtimestamp(time.time() + s.offset_sec, tz=KST)
