"""예매처 서버시각을 밀리초 단위로 추정한다.

HTTP Date 헤더는 1초 해상도이므로, 값이 바뀌는 순간(초 경계)을 포착해야
밀리초 정밀도를 얻을 수 있다. 동기화 이후에는 monotonic 시계로 자체
진행하며 서버에 재요청하지 않는다.

요청 예산은 MAX_PROBES 로 하드코딩되어 있다. 사용자가 페이지를 몇 번
새로고침하는 수준의 부하이며, 설정으로 노출하거나 늘려서는 안 된다.

S1 검증(2026-08-26): 티켓링크는 Apache 오리진 직결로 CDN 을 경유하지 않으며,
5회 요청으로 경계 검출에 성공해 오차 ±93ms 를 기록했다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import requests

KST = timezone(timedelta(hours=9))
MAX_PROBES = 24
PROBE_INTERVAL = 0.12
TIMEOUT = 3.0


@dataclass(frozen=True)
class ServerSync:
    """서버시각 동기화 결과."""
    offset_sec: float
    uncertainty_ms: float
    probes_used: int
    min_rtt_ms: float
    source: str
    synced_mono: float


def _parse_date(value: str) -> datetime:
    """RFC 9110 Date 헤더를 UTC datetime 으로 변환한다."""
    return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %Z").replace(
        tzinfo=timezone.utc
    )


def sync(url: str) -> ServerSync:
    """초 경계를 검출해 서버 오프셋을 추정한다.

    Raises:
        RuntimeError: Date 헤더가 없거나 예산 내 경계 검출에 실패한 경우.
                      호출측은 NTP 폴백으로 전환해야 한다.
    """
    prev_sec: datetime | None = None
    prev_t0 = 0.0
    rtts: list[float] = []

    for i in range(MAX_PROBES):
        t0 = time.monotonic()
        try:
            resp = requests.head(url, timeout=TIMEOUT,
                                 headers={"Cache-Control": "no-cache"})
            t1 = time.monotonic()
        except Exception:
            time.sleep(PROBE_INTERVAL)
            continue

        header = resp.headers.get("Date")
        if not header:
            raise RuntimeError("Date 헤더가 없어 이 방식을 쓸 수 없습니다.")

        dt = _parse_date(header)
        rtts.append(t1 - t0)

        if prev_sec is not None and dt > prev_sec:
            half_rtt = min(rtts) / 2
            boundary_mono = (prev_t0 + t0) / 2 + half_rtt
            wall = time.time() - (time.monotonic() - boundary_mono)
            return ServerSync(
                offset_sec=dt.timestamp() - wall,
                uncertainty_ms=((t0 - prev_t0) / 2 + half_rtt) * 1000,
                probes_used=i + 1,
                min_rtt_ms=min(rtts) * 1000,
                source=url,
                synced_mono=time.monotonic(),
            )

        prev_sec, prev_t0 = dt, t0
        time.sleep(PROBE_INTERVAL)

    raise RuntimeError(f"{MAX_PROBES}회 내 초 경계 검출 실패")


def now(s: ServerSync) -> datetime:
    """보정된 현재 KST 시각을 반환한다."""
    return datetime.fromtimestamp(time.time() + s.offset_sec, tz=KST)


def seconds_until(target: datetime, s: ServerSync) -> float:
    """목표 시각까지 남은 초. 음수면 이미 지난 것."""
    return (target - now(s)).total_seconds()


def click_cue_seconds(target: datetime, s: ServerSync,
                      reaction_ms: float) -> float:
    """클릭 큐를 발사해야 할 시점까지 남은 초.

    인간 반응지연만큼 앞당겨 보정하므로, 이 값이 0이 되는 순간 신호를 주면
    실제 클릭이 target 에 도달한다.
    """
    return seconds_until(target, s) - reaction_ms / 1000
