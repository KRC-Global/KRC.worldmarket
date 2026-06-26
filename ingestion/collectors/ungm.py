"""UNGM 직접 API — developer.ungm.org (IFAD·FAO·WFP 등 UN 기관 발주공고).

KRC.worldmarket 의 _collect_ungm 이식. UNGM 공개 스크래핑 경로(/Public/Notice/Search)는
ADB/AfDB 만 안정적이며, IFAD/FAO/WFP 등은 developer.ungm.org 인증 API 로만 수집된다.
UNGM_API_KEY 미설정 시 빈 리스트 반환(파이프라인은 정상 진행).

(ADB·AfDB 는 ungm_common.collect_via_ungm 가 담당 — 여기서는 그 외 UN 기관.)
"""
from __future__ import annotations

import os

from . import _mdb_common as C

_API = "https://developer.ungm.org/api/v1/notices"
_PAGE_SIZE = 50
_MAX_PAGES = 6


def collect(limit: int = 50) -> list[dict]:
    api_key = os.environ.get("UNGM_API_KEY", "")
    if not api_key:
        print("  [UNGM] UNGM_API_KEY 미설정 — developer.ungm.org API 키 발급 후 수집 가능. (skip)")
        return []

    import requests as req

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    from datetime import datetime

    rows: list[dict] = []
    page = 0
    while page < _MAX_PAGES and len(rows) < limit:
        params = {
            "TenderStatusCode": "AC",
            "DeadlineFrom": datetime.utcnow().strftime("%Y-%m-%d"),
            "Keywords": "agriculture irrigation rural food consulting technical",
            "PageSize": _PAGE_SIZE, "PageIndex": page,
        }
        try:
            r = req.get(_API, headers=headers, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"  [UNGM] page {page} 오류: {e}")
            break

        items = data.get("Notices") or data.get("notices") or []
        if not items:
            break

        for item in items:
            title = (item.get("Title") or item.get("title") or "").strip()
            desc = item.get("Description") or item.get("description") or ""
            combined = f"{title} {desc}"
            if not C.is_agri(combined) and not C.is_consulting(combined):
                continue

            value_raw = item.get("EstimatedValue") or item.get("estimatedValue") or 0
            if value_raw and C.parse_value_usd(str(value_raw)) < C.MIN_VALUE_USD:
                continue

            deadline = (item.get("Deadline") or item.get("deadline") or "")[:10]
            if C.is_deadline_passed(deadline):
                continue
            posted = (item.get("PublishedDate") or item.get("Published")
                      or item.get("publishedDate") or "")
            if C.is_stale_date(posted, days=C.DEFAULT_FRESHNESS_DAYS):
                continue

            notice_id = item.get("Id") or item.get("id") or ""
            source_url = (item.get("NoticeUrl") or item.get("noticeUrl")
                          or item.get("Url") or "").strip()
            if not source_url:
                source_url = f"https://www.ungm.org/Public/Notice/{notice_id}"
            country = (item.get("Country") or item.get("country") or "").strip()
            org = (item.get("AgencyName") or item.get("agencyName")
                   or item.get("Beneficiary") or "UN")
            notice_type = (item.get("TypeName") or item.get("NoticeType")
                           or item.get("typeName") or "")
            agri = C.is_agri(combined)

            rows.append(C.to_normalized({
                "source": "ungm",
                "source_id": str(notice_id) if notice_id else None,
                "title": C.decorate_title(title, notice_type),
                "country": country,
                "client": org,
                "sector": "agriculture" if agri else "consulting",
                "notice_type": notice_type,
                "contract_value": C.fmt_value(value_raw) if value_raw else "",
                "deadline": deadline,
                "posted_date": posted[:10] if posted else None,
                "source_url": source_url,
                "raw_data": item,
            }))
            if len(rows) >= limit:
                break

        if len(items) < _PAGE_SIZE:
            break
        page += 1

    print(f"  [UNGM] {len(rows)}건 수집")
    return rows
