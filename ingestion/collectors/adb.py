"""ADB 발주공고 — UNGM 공개 검색 경유 (RSS 보다 안정적).

ADB 는 UNGM(www.ungm.org)에 공고를 게시한다. UNGM agency id=85 로 필터.
"""
from __future__ import annotations

from .ungm_common import collect_via_ungm


def collect(limit: int = 50) -> list[dict]:
    return collect_via_ungm("adb", limit)
