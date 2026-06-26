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
_ENRICH_BUDGET = 10  # 상세 페이지 fetch 상한 (마감/금액 보강)


def collect_via_ungm(source_key: str, limit: int = 50, enrich: bool = True) -> list[dict]:
    import requests as req
    from bs4 import BeautifulSoup

    agency_id = AGENCY_IDS.get(source_key)
    if not agency_id:
        return []

    from datetime import datetime

    display = _DISPLAY.get(source_key, source_key.upper())
    raw_rows: list[dict] = []  # KRC 스타일 dict (정규화 전 — 보강 가능)
    today = datetime.utcnow().strftime("%d-%b-%Y")
    page = 0  # UNGM PageIndex 는 0-base
    while page < _MAX_PAGES and len(raw_rows) < limit:
        # UNGM 검색 — 기관 필터(Agencies 배열) + IsActive/DeadlineFrom 으로 '활성 공고'만.
        # 단순 payload 는 마감 지난 옛 공고가 섞여 freshness/deadline 필터에 전부 탈락했음.
        payload = {
            "PageIndex": page, "PageSize": _PAGE_SIZE,
            "Title": "", "Description": "", "Reference": "",
            "PublishedFrom": "", "PublishedTo": "",
            "DeadlineFrom": today, "DeadlineTo": "",
            "Countries": [], "Agencies": [str(agency_id)], "UNSPSCs": [],
            "NoticeTypes": [], "SortField": "Deadline", "SortAscending": True,
            "isPicker": False, "IsSustainable": False, "IsActive": True,
            "NoticeDisplayType": None, "TypeOfCompetitions": [],
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
            # 제목은 .ungm-title (실제 공고명). 셀 텍스트엔 tooltip/"Open in a new window" 가 섞임.
            title_el = cells[1].select_one(".ungm-title") if len(cells) > 1 else None
            title = (title_el.get_text(strip=True) if title_el
                     else (cells[1].get_text(strip=True) if len(cells) > 1 else ""))
            import re as _re
            title = _re.sub(r"Open in a new window", "", title).strip()
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

            raw_rows.append({
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
            })
            if len(raw_rows) >= limit:
                break

        if len(table_rows) < _PAGE_SIZE:
            break
        page += 1

    # ── 상세 보강 — 마감일/금액이 비는 행을 공고 상세 페이지에서 후채움 ──
    # (목록 단계는 마감·금액이 종종 비어있음. 예산 내에서만 fetch.)
    fetch_detail = C.fetch_adb_detail if source_key == "adb" else C.fetch_afdb_detail
    rows: list[dict] = []
    budget = _ENRICH_BUDGET if enrich else 0
    import time
    for d in raw_rows:
        if budget > 0 and (not d.get("deadline") or not d.get("contract_value")):
            budget -= 1
            det = fetch_detail(d["source_url"])
            if det:
                if not d.get("contract_value") and det.get("contract_value"):
                    d["contract_value"] = det["contract_value"]
                if not d.get("deadline") and det.get("deadline"):
                    d["deadline"] = det["deadline"]
                if not d.get("procurement_method") and det.get("procurement_method"):
                    d["procurement_method"] = det["procurement_method"]
                if (not d.get("country")) and det.get("country"):
                    d["country"] = det["country"]
                if det.get("text_excerpt"):
                    d["raw_data"]["text_excerpt"] = det["text_excerpt"]
            if C.is_deadline_passed(d.get("deadline", "")):
                continue
            time.sleep(0.4)  # rate-limit 보호
        rows.append(C.to_normalized(d))

    print(f"  [{source_key}-UNGM] {len(rows)}건 수집")
    return rows
