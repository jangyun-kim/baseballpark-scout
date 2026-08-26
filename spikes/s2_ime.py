"""S2 - Chrome 환경에서 한/영 IME 변환모드 조회 가능성 검증.

한/영 전환은 키보드 레이아웃이 아니라 IME 변환 모드다.
Chrome은 TSF 기반이라 표준 ImmGetConversionStatus로는 타 프로세스 상태를
읽을 수 없다. 각 창에 딸린 숨은 IME 창에 WM_IME_CONTROL을 보내는 우회를 검증한다.

실행 방법:
  1. Chrome을 띄우고 아무 입력창(예: 검색창)을 클릭해 커서를 둔다
  2. 이 스크립트를 별도 콘솔에서 실행한다
  3. Chrome 입력창에서 한/영 키를 10회 눌러가며 콘솔 출력이 따라오는지 본다

통과 기준: 한/영 토글 10회 왕복 모두 정확히 반영
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

WM_IME_CONTROL = 0x0283
IMC_GETCONVERSIONMODE = 0x0001
IME_CMODE_NATIVE = 0x0001
VK_CAPITAL = 0x14

user32 = ctypes.WinDLL("user32", use_last_error=True)
imm32 = ctypes.WinDLL("imm32", use_last_error=True)
imm32.ImmGetDefaultIMEWnd.restype = wintypes.HWND
imm32.ImmGetDefaultIMEWnd.argtypes = [wintypes.HWND]


def foreground_title() -> str:
    """현재 포그라운드 창의 제목을 반환한다."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "(없음)"
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value or "(제목없음)"


def get_ime_mode() -> str | None:
    """'한' | '영' | None(판정불가) 을 반환한다."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    ime_hwnd = imm32.ImmGetDefaultIMEWnd(hwnd)
    if not ime_hwnd:
        return None

    try:
        mode = user32.SendMessageW(ime_hwnd, WM_IME_CONTROL,
                                   IMC_GETCONVERSIONMODE, 0)
    except Exception:
        return None

    if mode is None:
        return None
    return "한" if mode & IME_CMODE_NATIVE else "영"


def caps_on() -> bool:
    """CapsLock 상태를 반환한다."""
    return bool(user32.GetKeyState(VK_CAPITAL) & 0x0001)


if __name__ == "__main__":
    print("=" * 56)
    print("S2  한/영 IME 변환모드 조회 검증")
    print("=" * 56)
    print("\nChrome 입력창을 클릭한 뒤 한/영 키를 눌러보세요.")
    print("판정불가가 계속 나오면 이 방식은 Chrome에서 동작하지 않는 것입니다.")
    print("종료: Ctrl+C\n")

    last = object()
    unknown_streak = 0
    try:
        while True:
            mode = get_ime_mode()
            state = (mode, caps_on(), foreground_title()[:40])
            if state != last:
                m = mode if mode else "판정불가"
                caps = "ON" if state[1] else "off"
                print(f"  [{m:^4}]  CapsLock {caps:<3}  창: {state[2]}")
                last = state

            unknown_streak = unknown_streak + 1 if mode is None else 0
            if unknown_streak == 40:
                print("\n  경고: 판정불가가 지속됩니다. 대안 설계로 전환을 검토하세요.")
            time.sleep(0.15)
    except KeyboardInterrupt:
        print("\n종료")
