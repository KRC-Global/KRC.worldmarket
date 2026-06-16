"""ADB·AfDB 공통 수집기 — UNGM 공개 HTML 검색(AJAX) 경유.

KRC.worldmarket 의 _collect_via_ungm 이식. UNGM 의 기관별 공고 검색 결과 HTML
(div.tableRow / div.tableCell)을 파싱한다. 농업/컨설팅 키워드로 필터.
"""
from __future__ import annotations

from . import _mdb_common as C

AGENCY_IDS = {"adb": 85, "afdb": 84}
_DISPLAY = {"adb": "ADB", "afdb": "AfDB"}
_SEARCH_URL = "https://www.ungm.org/Public/Notice/Search"
_MAX_PAGES = 3
_PAGE_SIZE = 15


def collect_via_ungm(source_key: str, limit: int = 50) -> list[dict]:
    import requests as req
    from bs4 import BeautifulSoup

    agency_id = AGENCY_IDS.get(source_key)
    if not agency_id:
        return []

    display = _DISPLAY.get(source_key, source_key.upper())
    rows: list[dict] = []
    page = 1
    while page <= _MAX_PAGES and len(rows) < limit:
        # UNGM 검색은 기관 필터를 `Agencies`(배열)로 받는다. 과거 `AgencyId`(단수)는
        # 무시돼 전체 최신 공고가 반환됐다(ADB/AfDB 결과가 동일해지는 원인).
        payload = {
            "PageIndex": page, "PageSize": _PAGE_SIZE,
            "SortField": "DatePublished", "SortOrder": "desc",
            "UNSPSCCodes": "", "Agencies": [agency_id], "Keywords": "",
        }
        try:
            r = req.post(
                _SEARCH_URL, json=payload,
                headers={**C.browser_headers(referer="https://www.ungm.org/"),
                         "Content-Type": "application/json",
                         "Accept": "text/html, */*; q=0.01",
                         "X-Requested-With": "XMLHttpRequest"},
                timeout=20,
            )
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"  [{source_key}-UNGM] page {page} 오류: {e}")
            break

        soup = BeautifulSoup(r.text, "html.parser")
        table_rows = soup.select("div.tableRow")
        if not table_rows:
            break

        for row in table_rows:
            cells = row.select("div.tableCell")
            if len(cells) < 6:
                continue
            notice_id = row.get("data-noticeid", "")
            title = cells[1].get_text(strip=True) if len(cells) > 1 else ""
            if not title or not notice_id:
                continue

            deadline_raw = cells[2].get_text(strip=True) if len(cells) > 2 else ""
            deadline = deadline_raw.split()[0] if deadline_raw else ""
            if C.is_deadline_passed(deadline):
                continue
            posted_raw = cells[3].get_text(strip=True) if len(cells) > 3 else ""
            if C.is_stale_date(posted_raw, days=C.DEFAULT_FRESHNESS_DAYS):
                continue

            agency = cells[4].get_text(strip=True) if len(cells) > 4 else display
            notice_type = cells[5].get_text(strip=True) if len(cells) > 5 else ""
            country = cells[7].get_text(strip=True) if len(cells) > 7 else ""
            if country == "Multiple destinations":
                country = ""

            combined = f"{title} {notice_type}"
            if not C.is_agri(combined) and not C.is_consulting(combined):
                continue

            rows.append(C.to_normalized({
                "source": source_key,
                "source_id": notice_id,
                "title": C.decorate_title(title, notice_type),
                "country": country,
                "client": agency or display,
                "sector": ("consulting" if C.is_consulting(combined) and not C.is_agri(combined)
                           else "agriculture"),
                "notice_type": notice_type,
                "contract_value": C.extract_value_from_text(title),
                "deadline": deadline,
                "posted_date": posted_raw[:10] if posted_raw else None,
                "source_url": f"https://www.ungm.org/Public/Notice/{notice_id}",
                "raw_data": {"ungm_id": notice_id, "title": title,
                             "notice_type": notice_type, "posted": posted_raw, "agency": agency},
            }))
            if len(rows) >= limit:
                break

        if len(table_rows) < _PAGE_SIZE:
            break
        page += 1

    print(f"  [{source_key}-UNGM] {len(rows)}건 수집")
    return rows
