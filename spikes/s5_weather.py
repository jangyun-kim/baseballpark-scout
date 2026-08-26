"""S5 - 기상청 단기예보 API 연동 검증 (이중 인코딩 수정판).

공공데이터포털이 발급하는 서비스키에는 이미 URL 인코딩이 적용돼 있다
(%2F, %3D 등). 이를 requests 의 params 로 넘기면 한 번 더 인코딩되어
%252F 가 되고 서버가 403 을 반환한다.

해결: 키를 unquote 로 디코딩한 뒤 넘긴다. Decoding 키를 발급받은 경우는
그대로 넘기면 되므로, 아래 normalize_key() 가 두 경우를 모두 처리한다.

보안: 예외 메시지에 URL 을 노출하지 않는다. 서비스키가 로그에 남으면 안 된다.

통과 기준: 두 구장 모두 POP(강수확률)와 TMP(기온) 정상 수신
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import requests
from dotenv import load_dotenv

load_dotenv()
KST = timezone(timedelta(hours=9))
ENDPOINT = ("https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"
            "/getVilageFcst")

# 기상청 격자 좌표(nx, ny). 위경도가 아닌 기상청 전용 격자값.
GRID = {
    "라팍": {"nx": 89, "ny": 90},
    "잠실": {"nx": 62, "ny": 126},
}


def normalize_key(raw: str) -> str:
    """Encoding 키든 Decoding 키든 원본 형태로 되돌린다.

    unquote 를 적용해도 변화가 없으면 이미 디코딩된 키이므로 그대로 쓴다.
    """
    decoded = unquote(raw)
    return decoded


def base_datetime() -> tuple[str, str]:
    """가장 최근 단기예보 발표 시각을 반환한다.

    발표는 02/05/08/11/14/17/20/23시이며 약 10분 뒤부터 조회 가능하다.
    안전하게 45분 여유를 둔다.
    """
    now = datetime.now(KST) - timedelta(minutes=45)
    for h in (23, 20, 17, 14, 11, 8, 5, 2):
        if now.hour >= h:
            return now.strftime("%Y%m%d"), f"{h:02d}00"
    prev = now - timedelta(days=1)
    return prev.strftime("%Y%m%d"), "2300"


def fetch(name: str, nx: int, ny: int, key: str) -> dict[str, str]:
    """해당 격자의 POP/TMP/SKY/PTY 최근값을 반환한다.

    Raises:
        RuntimeError: 요청 실패 또는 API 오류. URL 은 메시지에 넣지 않는다.
    """
    base_date, base_time = base_datetime()
    params = {
        "serviceKey": key,
        "numOfRows": 300,
        "pageNo": 1,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    try:
        r = requests.get(ENDPOINT, params=params, timeout=10)
    except Exception as exc:
        raise RuntimeError(f"{name} 네트워크 오류: {type(exc).__name__}") from None

    if r.status_code != 200:
        raise RuntimeError(f"{name} HTTP {r.status_code} - 서비스키 또는 승인 상태 확인")

    text = r.text.strip()
    if text.startswith("<"):
        hint = "SERVICE_KEY" if "SERVICE" in text.upper() else "XML 오류 응답"
        raise RuntimeError(f"{name} JSON 아님 ({hint}) - 활용신청 승인 여부 확인")

    try:
        body = r.json()
        header = body["response"]["header"]
    except Exception:
        raise RuntimeError(f"{name} 응답 파싱 실패") from None

    if header.get("resultCode") not in ("00", "0"):
        raise RuntimeError(f"{name} API 오류: {header.get('resultMsg')}")

    items = body["response"]["body"]["items"]["item"]
    out: dict[str, str] = {}
    for it in items:
        cat = it["category"]
        if cat in ("POP", "TMP", "SKY", "PTY") and cat not in out:
            out[cat] = f"{it['fcstValue']} ({it['fcstDate']} {it['fcstTime']})"
    return out


if __name__ == "__main__":
    print("=" * 56)
    print("S5  기상청 단기예보 API 연동 검증")
    print("=" * 56)

    raw = os.getenv("KMA_SERVICE_KEY")
    if not raw:
        print("\n실패: .env 에 KMA_SERVICE_KEY 가 없습니다.")
        raise SystemExit(1)

    key = normalize_key(raw)
    changed = "예 (Encoding 키로 판단)" if key != raw else "아니오 (Decoding 키)"
    print(f"\n서비스키 디코딩 적용: {changed}")

    bd, bt = base_datetime()
    print(f"기준 발표시각      : {bd} {bt}\n")

    ok = True
    for name, g in GRID.items():
        try:
            res = fetch(name, g["nx"], g["ny"], key)
            print(f"  [{name}] nx={g['nx']} ny={g['ny']}")
            for k, label in (("TMP", "기온"), ("POP", "강수확률"),
                             ("SKY", "하늘상태"), ("PTY", "강수형태")):
                print(f"    {label:<6}: {res.get(k, '없음')}")
            if "POP" not in res or "TMP" not in res:
                ok = False
        except RuntimeError as exc:
            print(f"  [{name}] 실패: {exc}")
            ok = False
        print()

    print(f"  판정: {'통과' if ok else '미달'}")
    raise SystemExit(0 if ok else 1)