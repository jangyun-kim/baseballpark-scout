"""예매 준비 상태를 점검한다.

전부 읽기 전용이며 예매 사이트와 통신하지 않는다. 내 PC 상태만 조회한다.
각 점검은 (상태, 표시값, 조치) 세 값을 돌려주고, 상태는
ok / warn / bad / unknown 중 하나다.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

import psutil

from . import ime

OK, WARN, BAD, UNKNOWN = "ok", "warn", "bad", "unknown"


@dataclass(frozen=True)
class Check:
    """단일 점검 결과."""
    name: str
    state: str
    value: str
    action: str = ""


def check_ime() -> Check:
    """한/영 입력 상태. 예매 직전에는 영문이어야 한다."""
    if not ime.available():
        return Check("한/영 입력", UNKNOWN, "Windows 전용")

    mode = ime.ime_mode()
    if mode is None:
        return Check("한/영 입력", UNKNOWN, "판정불가",
                     "오픈 30초 전 한/영 키를 1회 눌러 영문으로 확정하세요")
    if mode == "한":
        return Check("한/영 입력", BAD, "[한]", "영문으로 전환하세요")
    return Check("한/영 입력", OK, "[영]")


def check_caps() -> Check:
    """CapsLock 상태."""
    on = ime.caps_lock_on()
    if on is None:
        return Check("CapsLock", UNKNOWN, "조회불가")
    if on:
        return Check("CapsLock", BAD, "ON", "CapsLock 을 끄세요")
    return Check("CapsLock", OK, "off")


def check_cpu(threshold: float = 60.0) -> Check:
    """CPU 여유. 예매 순간의 렌더링 지연을 줄이기 위함."""
    used = psutil.cpu_percent(interval=0.3)
    if used >= threshold:
        return Check("CPU 사용률", WARN, f"{used:.0f}%",
                     "불필요한 프로그램과 크롬 탭을 정리하세요")
    return Check("CPU 사용률", OK, f"{used:.0f}%")


def check_memory(threshold: float = 85.0) -> Check:
    """메모리 여유."""
    used = psutil.virtual_memory().percent
    if used >= threshold:
        return Check("메모리 사용률", WARN, f"{used:.0f}%",
                     "메모리를 점유하는 앱을 종료하세요")
    return Check("메모리 사용률", OK, f"{used:.0f}%")


def check_power() -> Check:
    """전원 계획. 절전 모드는 CPU 부스트를 제한한다."""
    if sys.platform != "win32" or not shutil.which("powercfg"):
        return Check("전원 계획", UNKNOWN, "조회불가")

    try:
        out = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return Check("전원 계획", UNKNOWN, "조회실패")

    lowered = out.lower()
    if "절전" in out or "power saver" in lowered:
        return Check("전원 계획", WARN, "절전",
                     "고성능 또는 균형 조정으로 바꾸세요")
    return Check("전원 계획", OK, out.split("(")[-1].strip(") \r\n") or "확인됨")


def check_battery() -> Check:
    """배터리 연결 상태. 노트북이 아니면 항상 ok."""
    b = psutil.sensors_battery()
    if b is None:
        return Check("전원 연결", OK, "데스크톱")
    if not b.power_plugged:
        return Check("전원 연결", WARN, f"배터리 {b.percent:.0f}%",
                     "전원 어댑터를 연결하세요")
    return Check("전원 연결", OK, "어댑터 연결됨")


def check_zoom(current: int | None, optimal: int | None) -> Check:
    """브라우저 배율. 확장 브리지에서 받은 값과 캘리브레이션 값을 비교한다."""
    if current is None:
        return Check("브라우저 배율", UNKNOWN, "확장 미연결",
                     "Chrome 확장을 로드하고 브리지를 실행하세요")
    if optimal is None:
        return Check("브라우저 배율", WARN, f"{current}%",
                     "리허설로 최적 배율을 먼저 캘리브레이션하세요")
    if current == optimal:
        return Check("브라우저 배율", OK, f"{current}% (최적)")
    return Check("브라우저 배율", BAD, f"{current}%",
                 f"{optimal}% 로 조정하세요 (스크롤 발생 예상)")


def check_sync(uncertainty_ms: float | None,
               ntp_delta_sec: float | None) -> Check:
    """서버시각 동기화 상태와 NTP 교차검증 결과."""
    if uncertainty_ms is None:
        return Check("서버시각 동기화", BAD, "미동기화", "동기화를 실행하세요")

    value = f"±{uncertainty_ms:.0f}ms"
    if ntp_delta_sec is not None:
        value += f"  NTP Δ{ntp_delta_sec:+.2f}s"
        if abs(ntp_delta_sec) > 1.0:
            return Check("서버시각 동기화", WARN, value,
                         "서버시각과 NTP 차이가 큽니다. 재동기화를 권합니다")

    if uncertainty_ms > 200:
        return Check("서버시각 동기화", WARN, value, "재동기화를 권합니다")
    return Check("서버시각 동기화", OK, value)


def run_all(zoom_current: int | None = None,
            zoom_optimal: int | None = None,
            uncertainty_ms: float | None = None,
            ntp_delta_sec: float | None = None) -> list[Check]:
    """전체 점검을 실행해 결과 목록을 반환한다."""
    return [
        check_sync(uncertainty_ms, ntp_delta_sec),
        check_zoom(zoom_current, zoom_optimal),
        check_ime(),
        check_caps(),
        check_cpu(),
        check_memory(),
        check_power(),
        check_battery(),
    ]


def summary(checks: list[Check]) -> tuple[str, int]:
    """전체 상태와 조치 필요 항목 수를 반환한다."""
    bad = sum(1 for c in checks if c.state == BAD)
    warn = sum(1 for c in checks if c.state == WARN)
    if bad:
        return BAD, bad + warn
    if warn:
        return WARN, warn
    return OK, 0
