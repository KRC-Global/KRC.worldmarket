"""World Bank 발주공고 수집 — 공식 Procurement Notices JSON API (인증 불필요).

KRC.worldmarket 의 검증된 수집기를 이식. 페이지네이션 + 농업 필터 +
마감/신선도 필터 + notice_text 상세 파싱(금액·scope) 포함.
"""
from __future__ import annotations

from . import _mdb_common as C

API = "https://search.worldbank.org/api/procnotices"
_MAX_TOTAL = 500
_PAGE = 100


def collect(limit: int = 50) -> list[dict]:
    import requests as req

    rows: list[dict] = []
    offset = 0
    while offset < _MAX_TOTAL and len(rows) < limit:
        params = {
            "format": "json", "apilang": "en", "rows": _PAGE, "os": offset,
            "srt": "submission_date", "strdesc": "desc",
        }
        r = req.get(API, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        raw = data.get("procnotices") or []
        items = list(raw.values()) if isinstance(raw, dict) else raw
        if not items:
            break

        for item in items:
            title = (item.get("project_name") or item.get("bid_description") or "").strip()
            if not title:
                continue
            notice_type = (item.get("notice_type") or "").strip()
            if notice_type.lower() == "contract award":
                continue
            if not C.is_agri(f"{title} {item.get('bid_description') or ''}"):
                continue
            if (item.get("notice_status") or "").lower() in ("closed", "cancelled", "canceled"):
                continue
            nid = (item.get("id") or "").strip()
            if not nid:
                continue

            deadline_raw = (item.get("submission_deadline_date")
                            or item.get("submission_date")
                            or item.get("noticedate") or "")
            deadline = deadline_raw[:10] if deadline_raw else ""
            if C.is_deadline_passed(deadline):
                continue
            posted = (item.get("noticedate") or item.get("submission_date") or "")
            if C.is_stale_date(posted, days=C.DEFAULT_FRESHNESS_DAYS):
                continue

            wb_details = C.wb_extract_details(item.get("notice_text", ""))
            contract_value = (wb_details.get("contract_amount")
                              or C.extract_value_from_text(item.get("notice_text", "")))
            if item.get("project_id"):
                wb_details["project_id"] = item["project_id"]
            raw_light = {k: v for k, v in item.items() if k != "notice_text"}
            raw_light["wb_details"] = wb_details

            rows.append(C.to_normalized({
                "source": "worldbank",
                "source_id": nid,
                "title": C.decorate_title(title, notice_type),
                "country": (item.get("project_ctry_name") or "").strip(),
                "region": (item.get("regionname") or "").strip(),
                "client": (item.get("contact_organization") or "").strip() or "World Bank",
                "sector": "agriculture",
                "notice_type": notice_type,
                "procurement_method": (wb_details.get("procurement_method")
                                       or item.get("procurement_method_name") or "").strip(),
                "procurement_category": (item.get("procurement_group_desc_exact") or "").strip(),
                "project_id": (item.get("project_id") or "").strip(),
                "project_name": title,
                "contract_value": contract_value,
                "deadline": deadline,
                "posted_date": posted[:10] if posted else None,
                "source_url": f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{nid}",
                "raw_data": raw_light,
            }))
            if len(rows) >= limit:
                break

        try:
            total = int(data.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        offset += len(items)
        if total and offset >= total:
            break

    return rows
