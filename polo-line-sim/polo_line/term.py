# -*- coding: utf-8 -*-
"""터미널 출력 유틸리티.

한글은 대부분 동아시아 넓은 글자(W)라 터미널에서 두 칸을 차지한다.
len() 으로 폭을 재면 표가 어긋나므로 이 모듈의 dwidth() 를 쓴다.
"""
from __future__ import annotations

import os
import sys
import unicodedata

# ---------------------------------------------------------------- 색상
_COLOR = True


def _enable_windows_vt() -> bool:
    """Windows 콘솔에서 ANSI 이스케이프를 활성화한다."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def init(use_color: bool = True) -> None:
    """표준 출력을 UTF-8 로 맞추고 색상 사용 여부를 정한다."""
    global _COLOR
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _COLOR = use_color and sys.stdout.isatty() and _enable_windows_vt()


_CODES = {
    "dim": "2",
    "bold": "1",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "cyan": "36",
    "grey": "90",
}


def c(text: str, *styles: str) -> str:
    """text 에 색/스타일을 입힌다. 색상이 꺼져 있으면 원문을 그대로 돌려준다."""
    if not _COLOR or not styles:
        return text
    codes = ";".join(_CODES[s] for s in styles if s in _CODES)
    return f"\033[{codes}m{text}\033[0m" if codes else text


def render(segments) -> str:
    """`[text, styles]` 쌍의 목록을 한 줄로 만든다 — live.frames() 의 출력 형식."""
    return "".join(c(text, *styles) for text, styles in segments)


# ---------------------------------------------------------------- 폭 계산
def dwidth(text: str) -> int:
    """터미널에서 차지하는 칸 수. ANSI 이스케이프는 폭 0 으로 센다."""
    width, i = 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "\033":  # ANSI 시퀀스 건너뛰기
            end = text.find("m", i)
            i = len(text) if end == -1 else end + 1
            continue
        if unicodedata.combining(ch):
            i += 1
            continue
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        i += 1
    return width


def pad(text: str, width: int, align: str = "left") -> str:
    """표시 폭 기준으로 text 를 width 칸에 맞춘다."""
    gap = max(0, width - dwidth(text))
    if align == "right":
        return " " * gap + text
    if align == "center":
        left = gap // 2
        return " " * left + text + " " * (gap - left)
    return text + " " * gap


# ---------------------------------------------------------------- 블록 요소
WIDTH = 96


def rule(char: str = "─", width: int = WIDTH) -> str:
    return c(char * width, "grey")


def title(text: str, subtitle: str = "") -> None:
    print()
    print(c("━" * WIDTH, "blue"))
    print(c(" " + text, "bold", "cyan"))
    if subtitle:
        print(c(" " + subtitle, "grey"))
    print(c("━" * WIDTH, "blue"))


def section(number: str, text: str) -> None:
    print()
    print(c(f" [{number}] ", "yellow") + c(text, "bold"))
    print(rule())


def note(text: str) -> None:
    print(c("   · " + text, "grey"))


def table(headers, rows, aligns=None, styles=None) -> None:
    """헤더 목록과 행 목록을 받아 정렬된 표를 그린다.

    aligns: 열별 'left'|'right'|'center'
    styles: 행 인덱스 -> 스타일 튜플 (행 전체에 적용)
    """
    aligns = aligns or ["left"] * len(headers)
    styles = styles or {}
    widths = [dwidth(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], dwidth(str(cell)))

    head = "  ".join(c(pad(h, widths[i], aligns[i]), "grey", "bold") for i, h in enumerate(headers))
    print("  " + head)
    print("  " + c("─" * (sum(widths) + 2 * (len(widths) - 1)), "grey"))
    for r, row in enumerate(rows):
        cells = [pad(str(cell), widths[i], aligns[i]) for i, cell in enumerate(row)]
        line = "  ".join(cells)
        print("  " + (c(line, *styles[r]) if r in styles else line))


def bar(value: float, maximum: float, width: int = 28, style: str = "cyan") -> str:
    """수평 막대. value/maximum 비율만큼 채운다."""
    if maximum <= 0:
        return " " * width
    filled = max(0, min(width, round(width * value / maximum)))
    return c("█" * filled, style) + c("░" * (width - filled), "grey")


def kv(label: str, value: str, label_width: int = 26) -> None:
    print("   " + c(pad(label, label_width), "grey") + value)
