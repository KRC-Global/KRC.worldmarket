"""공통 공고 스키마 + 농업분야 필터.

각 collector 는 아래 normalize() 가 반환하는 dict 형태로 공고를 내보낸다.
키는 db/schema.sql 의 notices 컬럼과 1:1 대응.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

# 농업분야 다국어 키워드 (소문자 매칭)
AG_KEYWORDS = [
    # EN
    "agriculture", "agricultural", "agri", "agribusiness", "agro", "agroforestry",
    "irrigation", "rural", "livestock", "fisheries", "fishery", "aquaculture",
    "food security", "crop", "horticulture", "farming", "farmer", "seed",
    # KO
    "농업", "관개", "축산", "수산", "농촌", "식량", "농식품", "농수산",
    # JA
    "農業", "灌漑", "農村", "漁業",
    # FR
    "élevage", "pêche", "agricole",
]

# 세부 분야 추정용 (우선순위 순)
SUBSECTOR_RULES = [
    ("관개/수자원", ["irrigation", "water", "관개", "灌漑"]),
    ("축산", ["livestock", "cattle", "dairy", "축산", "poultry"]),
    ("수산/양식", ["fisheries", "fishery", "aquaculture", "수산", "漁業", "pêche"]),
    ("농촌개발", ["rural", "농촌"]),
    ("작물/원예", ["crop", "horticulture", "seed", "작물", "원예"]),
    ("농식품/가치사슬", ["agribusiness", "food", "value chain", "농식품"]),
]


def is_agriculture(*texts: Optional[str]) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(kw.lower() in blob for kw in AG_KEYWORDS)


def guess_subsector(*texts: Optional[str]) -> Optional[str]:
    blob = " ".join(t for t in texts if t).lower()
    for label, kws in SUBSECTOR_RULES:
        if any(k in blob for k in kws):
            return label
    return None


def content_hash(*parts: Optional[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8", "ignore"))
    return h.hexdigest()


def normalize(
    *,
    source: str,
    source_notice_id: str,
    title: str,
    source_url: str,
    country: Optional[str] = None,
    country_iso: Optional[str] = None,
    sector: Optional[str] = None,
    notice_type: Optional[str] = None,
    procurement_method: Optional[str] = None,
    published_at: Optional[str] = None,
    deadline_at: Optional[str] = None,
    budget_amount: Optional[float] = None,
    budget_currency: Optional[str] = None,
    raw_text: Optional[str] = None,
    language: Optional[str] = None,
) -> dict:
    """collector 출력을 notices 행 dict 로 표준화."""
    return {
        "source": source,
        "source_notice_id": str(source_notice_id),
        "title": title.strip() if title else "(제목 없음)",
        "country": country,
        "country_iso": country_iso,
        "sector": sector,
        "ag_subsector": guess_subsector(title, sector, raw_text),
        "notice_type": notice_type,
        "procurement_method": procurement_method,
        "published_at": published_at,
        "deadline_at": deadline_at,
        "budget_amount": budget_amount,
        "budget_currency": budget_currency,
        "source_url": source_url,
        "raw_text": raw_text,
        "language": language,
        "content_hash": content_hash(source, source_notice_id, title, raw_text),
    }


_WS = re.compile(r"\s+")


def clean_text(s: Optional[str]) -> Optional[str]:
    if not s:
        return s
    return _WS.sub(" ", s).strip()
