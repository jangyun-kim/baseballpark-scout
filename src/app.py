"""baseballpark-scout - 티켓팅 타이밍 대시보드.

실행: streamlit run src/app.py

예매 행위는 일절 자동화하지 않는다. 이 앱이 하는 일은 셋뿐이다.
  1. 예매처 서버시각을 밀리초 단위로 맞춰 보여준다
  2. 클릭 큐를 사용자 반응지연만큼 앞당겨 발사한다
  3. 내 PC 준비 상태를 점검한다
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core import ntp_clock, server_time
from src.system import readiness, zoom_bridge

TARGET_URL = "https://www.ticketlink.co.kr"
BADGE = {"ok": "🟢", "warn": "🟡", "bad": "🔴", "unknown": "⚪"}

st.set_page_config(page_title="baseballpark-scout", layout="wide")


def _init() -> None:
    """세션 상태 기본값을 채운다."""
    defaults = {
        "sync": None,
        "ntp": None,
        "reaction_ms": 230.0,
        "zoom_optimal": None,
        "open_at": None,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


_init()
zoom_bridge.start()

st.title("baseballpark-scout")
st.caption("티켓팅 타이밍 도구 — 예매 행위는 자동화하지 않습니다")

left, right = st.columns([3, 2])

with left:
    st.subheader("서버시각")

    if st.button("동기화 실행", type="primary"):
        with st.spinner("초 경계 검출 중 (최대 3초)"):
            try:
                st.session_state.sync = server_time.sync(TARGET_URL)
            except RuntimeError as exc:
                st.session_state.sync = None
                st.error(f"서버시각 동기화 실패: {exc}")
            try:
                st.session_state.ntp = ntp_clock.sync()
            except RuntimeError:
                st.session_state.ntp = None

    s = st.session_state.sync
    if s is None:
        st.info("동기화를 먼저 실행하세요.")
        ntp_delta = None
        uncertainty = None
    else:
        uncertainty = s.uncertainty_ms
        n = st.session_state.ntp
        ntp_delta = (s.offset_sec - n.offset_sec) if n else None

        c1, c2, c3 = st.columns(3)
        c1.metric("서버시각", server_time.now(s).strftime("%H:%M:%S.%f")[:-3])
        c2.metric("추정 오차", f"±{s.uncertainty_ms:.0f} ms")
        c3.metric("최소 RTT", f"{s.min_rtt_ms:.0f} ms")

        if ntp_delta is not None:
            st.caption(f"NTP 교차검증 Δ {ntp_delta:+.3f}초 "
                       f"({st.session_state.ntp.server}) · "
                       f"요청 {s.probes_used}/{server_time.MAX_PROBES}회 사용")

    st.divider()
    st.subheader("오픈 카운트다운")

    col_d, col_t = st.columns(2)
    d = col_d.date_input("예매 오픈 날짜", datetime.now().date())
    t = col_t.time_input("오픈 시각", datetime.now().time().replace(second=0))

    st.session_state.reaction_ms = st.slider(
        "내 반응지연 (ms)", 100, 500, int(st.session_state.reaction_ms), 10,
        help="클릭 큐를 이만큼 앞당겨 발사합니다. 리허설로 측정한 값을 넣으세요.",
    )

    if s is not None:
        target = datetime.combine(d, t).replace(tzinfo=server_time.KST)
        st.session_state.open_at = target
        remain = server_time.seconds_until(target, s)
        cue = server_time.click_cue_seconds(
            target, s, st.session_state.reaction_ms)

        if remain < 0:
            st.warning(f"오픈 시각이 {abs(remain):.0f}초 지났습니다.")
        else:
            st.metric("오픈까지", str(timedelta(seconds=int(remain))))
            st.metric("클릭 큐까지", f"{cue:,.2f} 초")
            if remain < 60:
                st.progress(max(0.0, min(1.0, 1 - remain / 60)))

with right:
    st.subheader("예매 준비 상태판")

    zoom_now, zoom_url, bridge_ok = zoom_bridge.state.snapshot()
    st.session_state.zoom_optimal = st.number_input(
        "최적 배율 (%)", 25, 200,
        st.session_state.zoom_optimal or 100, 5,
        help="리허설에서 결제 버튼까지 스크롤 없이 보였던 최저 배율",
    )

    checks = readiness.run_all(
        zoom_current=zoom_now,
        zoom_optimal=st.session_state.zoom_optimal,
        uncertainty_ms=uncertainty,
        ntp_delta_sec=ntp_delta,
    )
    overall, pending = readiness.summary(checks)

    if overall == readiness.OK:
        st.success("준비 완료")
    elif overall == readiness.WARN:
        st.warning(f"확인 권장 {pending}건")
    else:
        st.error(f"조치 필요 {pending}건")

    for c in checks:
        st.markdown(f"{BADGE[c.state]} **{c.name}** — {c.value}")
        if c.action:
            st.caption(f"　→ {c.action}")

    if not bridge_ok:
        st.caption("확장이 연결되면 브라우저 배율이 표시됩니다.")

    if st.button("상태 새로고침"):
        st.rerun()

st.divider()
st.caption(
    "본 도구는 예매 페이지 자동 새로고침, 보안문자 자동 입력, 좌석 자동 선택, "
    "잔여석 스크래핑을 일절 수행하지 않습니다. "
    f"서버 요청은 동기화 시 최대 {server_time.MAX_PROBES}회로 제한됩니다."
)
