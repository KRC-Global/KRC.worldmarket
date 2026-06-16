"""KOICA 발주공고 — KOICA_API_KEY 있으면 data.go.kr OpenAPI, 없으면 nebid.koica.go.kr HTML 스크래핑.

KRC.worldmarket 의 _collect_koica 이식. 농업/컨설팅(용역) 키워드(영/한)로 필터.
"""
from __future__ import annotations

import os
import re

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
    from bs4 import BeautifulSoup

    list_url = "https://nebid.koica.go.kr/oep/bepb/beffatPblancList.do"
    rows: list[dict] = []
    seen: set[str] = set()
    try:
        r = req.get(list_url, headers=C.browser_headers(referer="https://nebid.koica.go.kr/"),
                    timeout=20, verify=False)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        table_rows = soup.select("tr.row[onclick]") or soup.select("tbody tr[onclick]")
        print(f"  [KOICA-nebid] rows: {len(table_rows)}")
    except Exception as e:  # noqa: BLE001
        print(f"  [KOICA-nebid] 오류: {e}")
        return rows

    for row in table_rows:
        m = re.search(r"beffatPblancInfoDetailInqire\('([^']+)'\)", row.get("onclick", ""))
        if not m:
            continue
        bid_no = m.group(1)
        detail_url = ("https://nebid.koica.go.kr/oep/bepb/"
                      f"beffatPblancInfoDetailInqire.do?pblancNo={bid_no}")
        if detail_url in seen:
            continue
        seen.add(detail_url)

        cols = [c.get_text(" ", strip=True) for c in row.select("td")]
        if len(cols) < 6:
            continue
        bid_kind, item_kind = cols[2], cols[3]
        title_td = row.select_one("td.left_T, td[title]")
        title = (title_td.get("title") if title_td and title_td.get("title")
                 else (cols[4] if len(cols) > 4 else ""))
        if not title:
            continue
        period = cols[5] if len(cols) > 5 else ""
        deadline_match = re.findall(r"\d{4}-\d{2}-\d{2}", period)
        deadline = deadline_match[-1] if deadline_match else ""
        if C.is_deadline_passed(deadline):
            continue
        posted = cols[-1] if cols else ""
        if C.is_stale_date(posted, days=C.DEFAULT_FRESHNESS_DAYS):
            continue

        combined = f"{title} {bid_kind} {item_kind}"
        agri_hit = C.is_agri(combined) or C.is_agri_ko(combined)
        cons_hit = C.is_consulting(combined) or C.is_consulting_ko(combined) or item_kind == "용역"
        if not agri_hit and not cons_hit:
            continue

        rows.append(C.to_normalized({
            "source": "koica",
            "source_id": bid_no,
            "title": C.decorate_title(title, bid_kind or item_kind),
            "country": "",
            "client": "KOICA",
            "sector": "agriculture" if agri_hit else "consulting",
            "notice_type": bid_kind,
            "contract_value": "",
            "deadline": deadline,
            "posted_date": posted[:10] if posted else None,
            "source_url": detail_url,
            "raw_data": {"bid_no": bid_no, "title": title, "bid_kind": bid_kind,
                         "item_kind": item_kind, "period": period, "posted": posted},
        }))
        if len(rows) >= limit:
            break
    return rows
