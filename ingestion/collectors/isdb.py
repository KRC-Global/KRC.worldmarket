"""IsDB(이슬람개발은행) 발주공고 — taxonomy 페이지에서 현재 활성 공고 수집.

KRC.worldmarket 의 _collect_isdb 이식. /project-procurement/tenders 기본 페이지는
마감된 EOI/PQN 위주라, GPN(term/207)·SPN(term/210,211) 카테고리 페이지를 직접 순회.
IsDB 는 비농업 오탐(변전소·냉동창고 등)이 많아 **농업 키워드 필수** 필터를 건다.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from . import _mdb_common as C

_PAGES = [
    ("https://www.isdb.org/project-procurement/taxonomy/term/207", "GPN"),
    ("https://www.isdb.org/project-procurement/taxonomy/term/210", "SPN"),
    ("https://www.isdb.org/project-procurement/taxonomy/term/211", "SPN"),
]
_TYPE_MAP = {"eoi": "EOI", "gpn": "GPN", "spn": "SPN",
             "ca": "Contract Award", "pq": "Pre-Qualification", "pqn": "Pre-Qualification"}
_COUNTRIES = (
    "Bangladesh", "Uganda", "Togo", "Benin", "Mauritania", "Guinea", "Morocco",
    "Kyrgyzstan", "Uzbekistan", "Tajikistan", "Turkey", "Türkiye", "Pakistan",
    "Indonesia", "Jordan", "Sierra Leone", "Suriname", "Azerbaijan", "Saudi Arabia",
    "Kazakhstan", "Egypt", "Nigeria", "Senegal", "Mali", "Burkina Faso", "Niger",
    "Cameroon", "Chad", "Mozambique", "Oman", "Tanzania",
)
_DETAIL_BUDGET = 15  # 상세 페이지 fetch 상한 (요청수 폭증 방지)


def collect(limit: int = 50) -> list[dict]:
    import requests as req
    from bs4 import BeautifulSoup

    rows: list[dict] = []
    seen: set[str] = set()
    current_year = datetime.utcnow().year

    for list_url, default_type in _PAGES:
        if len(rows) >= limit:
            break
        try:
            r = req.get(list_url, headers=C.browser_headers(referer="https://www.isdb.org/"), timeout=20)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"  [IsDB] {list_url} 오류: {e}")
            continue

        soup = BeautifulSoup(r.text, "html.parser")
        anchors = soup.select('a[href*="/project-procurement/tenders/"]')
        print(f"  [IsDB-{default_type}] anchors: {len(anchors)}")

        for a in anchors:
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or not href:
                continue
            if href.startswith("/"):
                href = "https://www.isdb.org" + href
            if href in seen:
                continue
            seen.add(href)

            notice_type = default_type
            ym = re.search(r"/tenders/(\d{4})/([a-z\-]+)/", href)
            url_year = None
            if ym:
                url_year = int(ym.group(1))
                notice_type = _TYPE_MAP.get(ym.group(2).lower(), notice_type)
            if url_year and url_year < current_year - 1:
                continue
            if notice_type == "Contract Award":
                continue

            parent = a.find_parent(["article", "div", "li"]) or a.parent
            row_text = parent.get_text(" ", strip=True) if parent else title
            if re.search(r"\b(Closed|Fermé|Fermé)\b", row_text, re.IGNORECASE):
                continue

            combined = f"{title} {row_text}"
            if not C.is_agri(combined):  # IsDB 는 농업 필수
                continue

            deadline = ""
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", row_text)
            if dm:
                deadline = dm.group(1)
            if not deadline:
                dm2 = re.search(
                    r"(?:Closing|Deadline|Close)\s*(?:Date)?[:\s]*"
                    r"(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s*\d{4})",
                    row_text, re.IGNORECASE)
                if dm2:
                    d = C.parse_date_any(dm2.group(1))
                    if d:
                        deadline = d.isoformat()
            if C.is_deadline_passed(deadline):
                continue

            country = next((kw for kw in _COUNTRIES if kw in row_text or kw in title), "")
            contract_value = C.extract_value_from_text(row_text)

            rows.append({
                "_isdb_raw": {
                    "source": "isdb",
                    "source_id": hashlib.md5(href.encode()).hexdigest()[:20],
                    "title": C.decorate_title(title, notice_type),
                    "country": country,
                    "client": "IsDB",
                    "sector": "agriculture",
                    "notice_type": notice_type,
                    "contract_value": contract_value,
                    "deadline": deadline,
                    "posted_date": None,
                    "source_url": href,
                    "raw_data": {"title": title, "url": href, "type": notice_type},
                },
                "_needs_detail": not contract_value,
            })
            if len(rows) >= limit:
                break

    # 금액 없는 항목 일부를 상세 페이지로 보강 (예산 내) + 마감/신선도 재검증
    budget = _DETAIL_BUDGET
    out: list[dict] = []
    for entry in rows:
        d = entry["_isdb_raw"]
        if entry["_needs_detail"] and budget > 0:
            budget -= 1
            det = C.fetch_adb_detail(d["source_url"])  # 범용 라벨 추출 재사용
            if det.get("contract_value"):
                d["contract_value"] = det["contract_value"]
            if not d["deadline"] and det.get("deadline"):
                d["deadline"] = det["deadline"]
                if C.is_deadline_passed(d["deadline"]):
                    continue
        out.append(C.to_normalized(d))

    print(f"  [IsDB] {len(out)}건 수집")
    return out
