"""포그라운드 창의 한/영 입력 상태와 CapsLock 을 조회한다.

한/영 전환은 키보드 레이아웃이 아니라 IME 변환 모드다. Chrome 은 TSF
기반이라 표준 ImmGetConversionStatus 로는 타 프로세스 상태를 읽을 수 없어,
각 창에 딸린 숨은 IME 창에 WM_IME_CONTROL 을 보내는 방식을 쓴다.

S2 검증(2026-08-26): Chrome 및 티켓링크 예매 창에서 한/영 토글 정상 감지.
Windows 전용이며 다른 OS 에서는 항상 None 을 반환한다.
"""
from __future__ import annotations

import sys

WM_IME_CONTROL = 0x0283
IMC_GETCONVERSIONMODE = 0x0001
IME_CMODE_NATIVE = 0x0001
VK_CAPITAL = 0x14

_AVAILABLE = sys.platform == "win32"

if _AVAILABLE:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _imm32 = ctypes.WinDLL("imm32", use_last_error=True)
    _imm32.ImmGetDefaultIMEWnd.restype = wintypes.HWND
    _imm32.ImmGetDefaultIMEWnd.argtypes = [wintypes.HWND]


def available() -> bool:
    """이 모듈을 쓸 수 있는 환경인지 반환한다."""
    return _AVAILABLE


def foreground_title() -> str:
    """포그라운드 창 제목. 조회 불가 시 빈 문자열."""
    if not _AVAILABLE:
        return ""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return ""
    n = _user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    _user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value or ""


def ime_mode() -> str | None:
    """'한' | '영' | None(판정불가)."""
    if not _AVAILABLE:
        return None

    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None

    ime_hwnd = _imm32.ImmGetDefaultIMEWnd(hwnd)
    if not ime_hwnd:
        return None

    try:
        mode = _user32.SendMessageW(ime_hwnd, WM_IME_CONTROL,
                                    IMC_GETCONVERSIONMODE, 0)
    except Exception:
        return None

    if mode is None:
        return None
    return "한" if mode & IME_CMODE_NATIVE else "영"


def caps_lock_on() -> bool | None:
    """CapsLock 상태. 조회 불가 시 None."""
    if not _AVAILABLE:
        return None
    return bool(_user32.GetKeyState(VK_CAPITAL) & 0x0001)
