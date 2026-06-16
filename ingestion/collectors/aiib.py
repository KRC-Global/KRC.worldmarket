"""AIIB 발주공고 — project-procurement 정적 데이터(ppo-data-all.js) 파싱.

KRC.worldmarket 의 _collect_aiib 이식. 포털이 노출하는 ppoData JS 배열을
정규식으로 파싱한다(RSS 보다 안정적). 농업/컨설팅 키워드로 필터.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

from . import _mdb_common as C

DATA_URL = ("https://www.aiib.org/en/opportunities/business/"
            "project-procurement/_common/ppo-data-all.js")


def collect(limit: int = 50) -> list[dict]:
    import requests as req

    r = req.get(DATA_URL, headers=C.browser_headers(referer="https://www.aiib.org/"), timeout=15)
    r.raise_for_status()
    text = r.text

    m = re.search(r"ppoData\s*=\s*\[(.*)\]\s*;?\s*$", text, re.DOTALL)
    if not m:
        m = re.search(r"ppoData\s*=\s*\[(.*?)\];", text, re.DOTALL)
    if not m:
        raise RuntimeError("AIIB ppoData 배열을 찾지 못함")

    rows: list[dict] = []
    obj_rx = re.compile(r"\{([^{}]+)\}")
    field_rx = re.compile(r'(\w+)\s*:\s*"((?:[^"\\]|\\.)*)"')
    today = datetime.utcnow().date()

    for obj_match in obj_rx.finditer(m.group(1)):
        fields = {k: v for k, v in field_rx.findall(obj_match.group(1))}
        if not fields or (fields.get("ct") or "").strip() == "Contract Awards":
            continue

        project = (fields.get("pj") or "").strip()
        desc = (fields.get("ds") or "").strip()
        country = (fields.get("mb") or "").strip()
        sector_raw = (fields.get("st") or "").strip()
        notice_type = (fields.get("tp") or "").strip()
        posted = (fields.get("id") or "").strip()
        deadline = (fields.get("cd") or "").strip()
        price = (fields.get("pc") or "").strip()
        doc_path = (fields.get("dc") or "").strip()

        combined = f"{project} {desc} {sector_raw} {notice_type}"
        agri_hit = C.is_agri(combined) or sector_raw.lower() in ("water", "rural")
        cons_hit = C.is_consulting(combined)
        if not agri_hit and not cons_hit:
            continue
        if C.is_stale_date(posted, days=C.DEFAULT_FRESHNESS_DAYS):
            continue

        deadline_iso = ""
        if deadline:
            for fmt in ("%B %d, %Y", "%b %d, %Y"):
                try:
                    dd = datetime.strptime(deadline, fmt).date()
                    deadline_iso = None if dd < today else dd.isoformat()
                    break
                except ValueError:
                    continue
        if deadline_iso is None:
            continue

        if doc_path:
            source_url = ("https://www.aiib.org" + doc_path
                          if doc_path.startswith("/") else doc_path)
        else:
            fp = hashlib.md5(f"{project}|{country}|{notice_type}|{posted}".encode()).hexdigest()[:12]
            source_url = ("https://www.aiib.org/en/opportunities/business/"
                          f"project-procurement/list.html#{fp}")

        title = project or desc[:200] or notice_type
        if not title:
            continue

        rows.append(C.to_normalized({
            "source": "aiib",
            "source_id": hashlib.md5(f"{project}|{country}|{posted}".encode()).hexdigest()[:20],
            "title": C.decorate_title(title, notice_type),
            "country": country,
            "client": "AIIB",
            "sector": "consulting" if cons_hit and not agri_hit else "agriculture",
            "notice_type": notice_type,
            "contract_value": C.compact_currency_phrase(price),
            "deadline": deadline_iso or "",
            "posted_date": posted[:10] if posted else None,
            "source_url": source_url,
            "raw_data": fields,
        }))
        if len(rows) >= limit:
            break

    return rows
