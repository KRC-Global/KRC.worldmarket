"""EDCF 발주공고 — edcfkorea.go.kr 공고 목록 페이지 직접 파싱.

KRC.worldmarket 의 _collect_edcf 이식. 개도국발주/EDCF발주 공고를 농업·컨설팅·인프라
키워드(영/한)로 필터. 국가명은 영문 사전 + 한국어 매핑으로 추출.
"""
from __future__ import annotations

import re

from . import _mdb_common as C

_BASE = "https://www.edcfkorea.go.kr"
_LIST = f"{_BASE}/fe/HPHFFE065M01"
_MAX_PAGES = 5

_KO_COUNTRY = {
    "우즈베키스탄": "Uzbekistan", "라오스": "Laos", "몽골": "Mongolia",
    "캄보디아": "Cambodia", "에티오피아": "Ethiopia", "탄자니아": "Tanzania",
    "필리핀": "Philippines", "미얀마": "Myanmar", "베트남": "Vietnam",
    "인도네시아": "Indonesia", "방글라데시": "Bangladesh", "파키스탄": "Pakistan",
    "케냐": "Kenya", "르완다": "Rwanda", "가나": "Ghana", "세네갈": "Senegal",
    "이집트": "Egypt", "모로코": "Morocco", "네팔": "Nepal", "스리랑카": "Sri Lanka",
}


def collect(limit: int = 50) -> list[dict]:
    import requests as req
    from bs4 import BeautifulSoup

    rows: list[dict] = []
    seen: set[str] = set()

    for page in range(1, _MAX_PAGES + 1):
        url = f"{_LIST}?boardtypeid=162&isIframe=&pagesize=10&currentpage={page}"
        try:
            resp = req.get(url, headers=C.browser_headers(referer=_LIST), timeout=20)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"  [EDCF] page {page} 오류: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select("div.notice-list-item")
        if not items:
            break

        page_has_items = False
        for item in items:
            board_id = None
            title = ""
            for link in item.select('a[href*="HPHFFE066"]'):
                m = re.search(r"boardid=(\d+)", link.get("href", ""))
                if not m:
                    continue
                if board_id is None:
                    board_id = m.group(1)
                link_text = link.get_text(strip=True)
                if len(link_text) > len(title):
                    title = link_text
            if not board_id or not title:
                continue

            source_url = (f"{_BASE}/fe/HPHFFE066M01?isIframe="
                          f"&pagesize=10&boardtypeid=162&boardid={board_id}")
            if source_url in seen:
                continue
            seen.add(source_url)

            item_text = item.get_text(" ", strip=True)
            date_m = re.search(r"(\d{4}\.\d{2}\.\d{2})", item_text)
            posted_str = date_m.group(1).replace(".", "-") if date_m else ""
            if C.is_stale_date(posted_str, days=C.DEFAULT_FRESHNESS_DAYS):
                continue

            country = ""
            for kw in C.COUNTRY_COORDS:
                if len(kw) > 4 and kw in item_text:
                    country = kw
                    break
            if not country:
                for ko, en in _KO_COUNTRY.items():
                    if ko in item_text:
                        country = en
                        break

            combined = title + " " + item_text
            agri_hit = C.is_agri(combined) or C.is_agri_ko(combined)
            cons_hit = C.is_consulting(combined) or C.is_consulting_ko(combined)
            infra_hit = bool(re.search(
                r"\b(?:인프라|공사|건설|construction|infrastructure|교량|도로|수도)\b",
                combined, re.IGNORECASE))
            if not agri_hit and not cons_hit and not infra_hit:
                continue

            notice_type = ""
            if "개도국발주사업" in item_text:
                notice_type = "Procurement Notice (개도국발주)"
            elif "EDCF발주사업" in item_text:
                notice_type = "Procurement Notice (EDCF발주)"

            page_has_items = True
            rows.append(C.to_normalized({
                "source": "edcf",
                "source_id": f"edcf_{board_id}",
                "title": title,
                "country": country,
                "client": "EDCF",
                "sector": "agriculture" if agri_hit else "consulting",
                "notice_type": notice_type,
                "contract_value": "",
                "deadline": "",
                "posted_date": posted_str,
                "source_url": source_url,
                "raw_data": {"board_id": board_id, "title": title,
                             "posted": posted_str, "country": country},
            }))
            if len(rows) >= limit:
                break

        if not page_has_items or len(rows) >= limit:
            break

    print(f"  [EDCF] {len(rows)}건 수집")
    return rows
