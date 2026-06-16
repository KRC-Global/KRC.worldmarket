"""KOICA 발주공고 — KOICA_API_KEY 있으면 data.go.kr OpenAPI 로 수집.

KRC.worldmarket 의 _collect_koica 이식. 농업/컨설팅(용역) 키워드(영/한)로 필터.
공개 포털(nebid) 폴백은 팝업/JS 렌더라 requests 로 불가 → 키 사용 권장.
"""
from __future__ import annotations

import os

from . import _mdb_common as C


def collect(limit: int = 50) -> list[dict]:
    import requests as req

    service_key = os.environ.get("KOICA_API_KEY", "")
    if service_key:
        return _collect_api(req, service_key, limit)
    return _collect_nebid(req, limit)


def _collect_api(req, service_key: str, limit: int) -> list[dict]:
    rows: list[dict] = []
    url = "https://apis.data.go.kr/1390802/koica_bid/koicaBidList"
    params = {"serviceKey": service_key, "pageNo": 1, "numOfRows": 100, "type": "json"}
    try:
        r = req.get(url, params=params, timeout=12)
        r.raise_for_status()
        items = (r.json().get("response", {}).get("body", {})
                 .get("items", {}).get("item", []))
        if isinstance(items, dict):
            items = [items]
    except Exception as e:  # noqa: BLE001
        print(f"  [KOICA-API] 오류: {e}")
        return rows

    for item in items:
        title = (item.get("bidNm") or item.get("title") or "").strip()
        combined = title + " " + str(item)
        if not C.is_agri(combined) and not C.is_consulting(combined) \
                and not C.is_agri_ko(combined) and not C.is_consulting_ko(combined):
            continue
        status = (item.get("bidPblancSttusCode") or item.get("status") or "").strip()
        if status and not (status in ("01", "공고중", "OPEN", "ACTIVE") or "공고" in status):
            continue
        deadline = (item.get("bidClseDt") or "")[:10]
        if C.is_deadline_passed(deadline):
            continue
        posted = (item.get("bidPblancDt") or item.get("postDt") or "")[:10]
        if C.is_stale_date(posted, days=C.DEFAULT_FRESHNESS_DAYS):
            continue
        bid_no = item.get("bidNo") or item.get("id") or ""
        source_url = item.get("bidUrl") or item.get("url") or ""
        if not source_url and bid_no:
            source_url = f"https://www.koica.go.kr/koica_kr/bid/view/{bid_no}"
        if not source_url:
            continue
        notice_type = (item.get("bidPblancKndNm") or item.get("bidKndNm") or "").strip()
        agri = C.is_agri(combined) or C.is_agri_ko(combined)
        rows.append(C.to_normalized({
            "source": "koica",
            "source_id": str(bid_no) if bid_no else None,
            "title": C.decorate_title(title, notice_type),
            "country": (item.get("country") or "").strip(),
            "client": "KOICA",
            "sector": "agriculture" if agri else "consulting",
            "notice_type": notice_type,
            "contract_value": (item.get("bidAmt") or "").strip(),
            "deadline": deadline,
            "posted_date": posted,
            "source_url": source_url,
            "raw_data": item,
        }))
        if len(rows) >= limit:
            break
    return rows


def _collect_nebid(req, limit: int) -> list[dict]:
    """공개 포털(nebid.koica.go.kr) HTML 폴백.

    현재 nebid 공고 목록은 다단계 팝업/AJAX(`pblancPopupInqire`)로 렌더돼 단순
    requests 로는 개별 공고 행을 얻을 수 없다(초기 HTML 에는 카테고리 요약만 존재).
    안정적 수집 경로는 data.go.kr OpenAPI 이므로 KOICA_API_KEY 사용을 권장한다.
    헤드리스 브라우저(Playwright) 기반 스크래핑은 M2 단계 과제.
    """
    print("  [KOICA] KOICA_API_KEY(data.go.kr) 미설정 — 공개 포털은 팝업/JS 렌더라 "
          "requests 스크래핑 불가. 키 설정 시 OpenAPI 로 수집됩니다.")
    return []
