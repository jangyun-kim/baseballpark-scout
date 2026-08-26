"""S1 - 티켓링크 서버시각 확보 가능성 검증.

확인 항목:
  1. HTTP Date 응답 헤더가 존재하는가
  2. CDN을 경유하는가 (Server / Via / CF-Ray 헤더)
  3. 초 경계 검출로 밀리초 정밀도를 얻을 수 있는가

요청 예산은 MAX_PROBES(24회, 약 3초)로 하드코딩되어 있다.
사용자가 페이지를 몇 번 새로고침하는 수준의 부하이며, 이 값을 늘려서는 안 된다.

통과 기준: Date 헤더 존재 + 추정 오차 200ms 미만
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

TARGET = "https://www.ticketlink.co.kr"
MAX_PROBES = 24
PROBE_INTERVAL = 0.12
TIMEOUT = 3.0


def inspect_headers() -> dict:
    """대상 서버의 헤더를 1회 조회해 Date/CDN 정보를 반환한다."""
    try:
        r = requests.head(TARGET, timeout=TIMEOUT,
                          headers={"Cache-Control": "no-cache"})
    except Exception as exc:
        raise RuntimeError(f"요청 실패: {exc}") from exc

    return {
        "status": r.status_code,
        "Date": r.headers.get("Date"),
        "Server": r.headers.get("Server"),
        "Via": r.headers.get("Via"),
        "CF-Ray": r.headers.get("CF-Ray"),
        "X-Cache": r.headers.get("X-Cache"),
        "Age": r.headers.get("Age"),
    }


def parse_date(value: str) -> datetime:
    """RFC 9110 Date 헤더를 UTC datetime으로 변환한다."""
    return datetime.strptime(value, "%a, %d %b %Y %H:%M:%S %Z").replace(
        tzinfo=timezone.utc
    )


def detect_boundary() -> dict:
    """초 경계를 검출해 서버 오프셋과 추정 오차를 계산한다.

    Raises:
        RuntimeError: 요청 예산 내에 경계를 찾지 못한 경우.
    """
    prev_sec: datetime | None = None
    prev_t0 = 0.0
    rtts: list[float] = []
    failures = 0

    for i in range(MAX_PROBES):
        t0 = time.monotonic()
        try:
            r = requests.head(TARGET, timeout=TIMEOUT,
                              headers={"Cache-Control": "no-cache"})
            t1 = time.monotonic()
        except Exception:
            failures += 1
            time.sleep(PROBE_INTERVAL)
            continue

        hdr = r.headers.get("Date")
        if not hdr:
            raise RuntimeError("Date 헤더가 없습니다. 이 방식은 사용할 수 없습니다.")

        dt = parse_date(hdr)
        rtts.append(t1 - t0)

        if prev_sec is not None and dt > prev_sec:
            half_rtt = min(rtts) / 2
            boundary_mono = (prev_t0 + t0) / 2 + half_rtt
            wall = time.time() - (time.monotonic() - boundary_mono)
            return {
                "offset_sec": dt.timestamp() - wall,
                "uncertainty_ms": ((t0 - prev_t0) / 2 + half_rtt) * 1000,
                "probes_used": i + 1,
                "failures": failures,
                "min_rtt_ms": min(rtts) * 1000,
            }

        prev_sec, prev_t0 = dt, t0
        time.sleep(PROBE_INTERVAL)

    raise RuntimeError(f"{MAX_PROBES}회 내 초 경계 검출 실패 - NTP 폴백 필요")


if __name__ == "__main__":
    print("=" * 56)
    print("S1  티켓링크 서버시각 확보 가능성 검증")
    print("=" * 56)

    print("\n[1] 헤더 조회")
    try:
        h = inspect_headers()
        for k, v in h.items():
            print(f"  {k:<10}: {v}")
    except RuntimeError as exc:
        print(f"  실패: {exc}")
        raise SystemExit(1)

    if not h["Date"]:
        print("\n  판정: 실패 - Date 헤더 없음")
        raise SystemExit(1)

    cdn = [k for k in ("Via", "CF-Ray", "X-Cache", "Age") if h.get(k)]
    print(f"\n  CDN 경유 흔적: {cdn if cdn else '없음'}")
    if cdn:
        print("  주의: 엣지 시각과 예매 서버 시각의 차이는 보정 불가")

    print("\n[2] 초 경계 검출")
    try:
        res = detect_boundary()
    except RuntimeError as exc:
        print(f"  실패: {exc}")
        raise SystemExit(1)

    print(f"  요청 사용     : {res['probes_used']}/{MAX_PROBES} (실패 {res['failures']})")
    print(f"  최소 RTT      : {res['min_rtt_ms']:.0f} ms")
    print(f"  서버-로컬 차이: {res['offset_sec']:+.3f} 초")
    print(f"  추정 오차     : ±{res['uncertainty_ms']:.0f} ms")

    ok = res["uncertainty_ms"] < 200
    print(f"\n  판정: {'통과' if ok else '미달'} (기준 200ms 미만)")
    raise SystemExit(0 if ok else 1)
