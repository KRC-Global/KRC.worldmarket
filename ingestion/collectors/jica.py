"""JICA 발주공고 — 스크래핑 (API 없음, 국가사무소 분산).
대상: jica.go.jp 본부 tender 페이지 + 국가사무소 bidding 페이지.
M2 단계에서 구현. 국가별 페이지 URL 리스트를 순회하며 PDF/공고 수집.
"""
from __future__ import annotations


def collect(limit: int = 50) -> list[dict]:
    raise NotImplementedError(
        "JICA 스크래퍼는 M2 단계에서 구현. 본부+국가사무소 tender 페이지 순회 필요."
    )
