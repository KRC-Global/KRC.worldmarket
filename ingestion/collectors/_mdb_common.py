"""MDB 수집기 공용 헬퍼.

KRC.worldmarket 의 검증된 수집 로직(키워드 필터·날짜/금액 파싱·HTML 정리·
브라우저 헤더·국가 매핑)을 발주공고 ingestion 구조로 이식한 모듈.

각 기관 collector 는 KRC 스타일 dict 를 만든 뒤 `to_normalized()` 로
normalize.normalize() 출력(= notices 행)으로 변환해 반환한다.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

from .. import normalize

DEFAULT_FRESHNESS_DAYS = 60

# ── 필터 키워드 ──────────────────────────────────────────────────────────────
AGRI_KEYWORDS = [
    "agriculture", "agricultural", "agri", "farming", "farm",
    "irrigation", "rural", "food security", "food and agriculture",
    "crop", "livestock", "rice", "grain", "seed", "fisheries",
    "forestry", "water resource", "drainage", "land reclamation",
    "watershed", "aquaculture", "paddy", "horticulture",
    "climate change", "climate adaptation",
    "reservoir", "dam", "dams",
    "rehabilitation", "refurbishment",
]
CONSULTING_KEYWORDS = [
    "consulting", "consultancy", "consultant", "technical assistance",
    "advisory", "supervision", "feasibility", "project management", "pmc",
    "f/s", "capacity building", "assessment", "planning",
    "engineering services", "detailed design", "design review",
    "design and supervision", "preliminary design",
]
AGRI_KEYWORDS_KO = [
    "농업", "농촌", "관개", "식량", "작물", "수산", "산림", "농지",
    "용수", "양식", "축산", "수자원", "간척", "개간",
    "기후변화", "저수지", "댐", "개보수",
]
CONSULTING_KEYWORDS_KO = [
    "용역", "기술용역", "컨설팅", "자문", "기술협력", "타당성",
    "기술지원", "기술조사", "사업관리", "조사연구", "기본설계", "실시설계",
    "PMC", "PMO", "TA",
]

_AGRI_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in AGRI_KEYWORDS) + r")(?:s|es)?\b",
    re.IGNORECASE,
)
_CONSULTING_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in CONSULTING_KEYWORDS) + r")(?:s|es)?\b",
    re.IGNORECASE,
)


def is_agri(text: str) -> bool:
    return bool(_AGRI_RE.search(text or ""))


def is_consulting(text: str) -> bool:
    return bool(_CONSULTING_RE.search(text or ""))


def is_agri_ko(text: str) -> bool:
    return any(kw in (text or "") for kw in AGRI_KEYWORDS_KO)


def is_consulting_ko(text: str) -> bool:
    return any(kw in (text or "") for kw in CONSULTING_KEYWORDS_KO)


# ── 날짜 파싱 ────────────────────────────────────────────────────────────────
_DATE_RX = re.compile(r"(\d{4})[-./\s년]\s*(\d{1,2})[-./\s월]\s*(\d{1,2})")


def parse_date_any(s: str):
    """YYYY-MM-DD / ISO datetime / Month DD YYYY / RFC822 / DD-Mon-YYYY → date."""
    if not s:
        return None
    raw = str(s).strip()
    try:
        iso = raw.replace("Z", "+00:00").split("T")[0]
        return datetime.fromisoformat(iso).date()
    except Exception:
        pass
    m = _DATE_RX.search(raw)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except Exception:
            pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        dt = parsedate_to_datetime(raw)
        if dt is not None:
            return dt.date()
    except (TypeError, ValueError):
        pass
    return None


def to_iso_date(s: str) -> Optional[str]:
    """날짜 문자열을 ISO(YYYY-MM-DD)로. 파싱 실패 시 None (Supabase timestamptz 안전)."""
    d = parse_date_any(s)
    return d.isoformat() if d else None


def is_deadline_passed(deadline_str: str) -> bool:
    d = parse_date_any(deadline_str)
    return bool(d and d < datetime.utcnow().date())


def is_stale_date(date_str: str, days: int = DEFAULT_FRESHNESS_DAYS) -> bool:
    if not date_str:
        return False
    d = parse_date_any(date_str)
    if d is None:
        return False
    return (datetime.utcnow().date() - d).days > days


# ── HTML / 헤더 ──────────────────────────────────────────────────────────────
def clean_html(text: str) -> str:
    if not text:
        return ""
    return re.sub(r"<[^>]+>", " ", str(text))


def browser_headers(referer: str = "") -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"
    return headers


def decorate_title(title: str, notice_type: str) -> str:
    title = (title or "").strip()
    notice_type = (notice_type or "").strip()
    if not notice_type:
        return title
    tag = f"[{notice_type}]"
    if tag.lower() in title.lower():
        return title
    return f"{title} {tag}"


# ── 금액 파싱 ────────────────────────────────────────────────────────────────
_CURRENCY_CODES = (
    "USD|US\\$|EUR|€|GBP|£|JPY|¥|CNY|RMB|KRW"
    r"|INR|IDR|PHP|THB|VND|MYR|SGD|HKD|TWD|PKR|BDT|LKR|NPR"
    r"|NGN|EGP|ZAR|KES|UGX|TZS|ETB|GHS|MAD|DZD|TND|XOF|XAF|MZN"
    r"|BRL|MXN|ARS|COP|CLP|PEN|AUD|NZD|CAD|CHF"
    r"|RUB|TRY|SAR|AED|QAR|KWD|OMR|BHD|KZT|KGS|UZS|TJS|AZN|GEL|LSL|BWP"
)
_VALUE_RX = re.compile(
    rf"({_CURRENCY_CODES})\s*([\d,\.]+)\s*(million|billion|mln|bn|M|B|K)?",
    re.IGNORECASE,
)
_VALUE_LABELED_RX = re.compile(
    rf"(?:Total\s+(?:Project\s+)?Cost|Contract\s+(?:Price|Value|Amount)|"
    rf"Estimated\s+(?:Cost|Value|Budget|Amount)|Loan\s+Amount|"
    rf"Project\s+(?:Budget|Cost)|Budget\s+Amount)"
    rf"[^\d\n]{{0,30}}?({_CURRENCY_CODES})\s*([\d,]+(?:\.\d+)?)\s*"
    rf"(million|billion|mln|bn|M|B|K)?",
    re.IGNORECASE,
)
_MIN_CONTRACT_USD_THRESHOLD = 10_000


def _format_compact_money(currency: str, raw_amount: str, unit: str = "",
                          min_threshold: float = 0) -> str:
    try:
        num = float(raw_amount.replace(",", ""))
    except (TypeError, ValueError):
        return ""
    unit_lower = (unit or "").lower()
    if unit_lower in ("billion", "bn", "b"):
        num *= 1_000_000_000
    elif unit_lower in ("million", "mln", "m"):
        num *= 1_000_000
    elif unit_lower in ("k",):
        num *= 1_000
    cur_raw = re.sub(
        r"(USD)+", "USD",
        (currency or "").upper().replace("US$", "USD").replace("$", "USD")
        .replace("€", "EUR").replace("£", "GBP"),
    )
    small_unit_currencies = {"IDR", "VND", "UZS", "KRW", "JPY", "PKR", "NGN",
                             "PHP", "KGS", "KZT", "UGX", "TZS", "LKR", "NPR", "BDT", "LSL"}
    threshold = min_threshold
    if cur_raw in small_unit_currencies and threshold:
        threshold = threshold * 10
    if threshold and num < threshold:
        return ""
    if num >= 1_000_000_000:
        amt = f"{num / 1_000_000_000:.1f}B"
    elif num >= 1_000_000:
        amt = f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        amt = f"{num / 1_000:.1f}K"
    else:
        amt = f"{num:,.0f}"
    return f"{cur_raw} {amt}".strip() if cur_raw else amt


def extract_value_from_text(text: str) -> str:
    if not text:
        return ""
    clean = clean_html(text)
    m = _VALUE_LABELED_RX.search(clean)
    if m:
        val = _format_compact_money(m.group(1), m.group(2), m.group(3),
                                    min_threshold=_MIN_CONTRACT_USD_THRESHOLD)
        if val:
            return val
    m = _VALUE_RX.search(clean)
    if m:
        return _format_compact_money(m.group(1), m.group(2), m.group(3),
                                     min_threshold=_MIN_CONTRACT_USD_THRESHOLD)
    return ""


def compact_currency_phrase(raw: str) -> str:
    if not raw:
        return ""
    parts = re.split(r"[\n;]+", raw.strip())
    first_match = None
    extra = 0
    for part in parts:
        m = _VALUE_RX.search(part)
        if m:
            if first_match is None:
                first_match = m
            else:
                extra += 1
    if not first_match:
        return raw[:60]
    compact = _format_compact_money(first_match.group(1), first_match.group(2),
                                    first_match.group(3))
    return compact + (f" (외 {extra}건)" if extra > 0 else "")


def parse_amount(contract_value: str) -> tuple:
    """'USD 2.3M' → (2300000.0, 'USD'). 실패 시 (None, None)."""
    if not contract_value:
        return None, None
    m = re.search(
        rf"({_CURRENCY_CODES})\s*([\d,\.]+)\s*(billion|million|mln|bn|B|M|K)?",
        contract_value, re.IGNORECASE,
    )
    if not m:
        return None, None
    cur = re.sub(r"(USD)+", "USD",
                 m.group(1).upper().replace("US$", "USD").replace("$", "USD"))
    try:
        num = float(m.group(2).replace(",", ""))
    except ValueError:
        return None, None
    unit = (m.group(3) or "").lower()
    if unit in ("billion", "bn", "b"):
        num *= 1_000_000_000
    elif unit in ("million", "mln", "m"):
        num *= 1_000_000
    elif unit == "k":
        num *= 1_000
    return num, cur


# ── World Bank notice_text 파서 ──────────────────────────────────────────────
_WB_STOP_LABELS = [
    "Scope of Contract", "Notice Version No", "Procurement Method",
    "Loan/Credit/TF Info", "Awarded Bidder(s)", "Duration of Contract",
    "Bid/Contract Reference No", "Contract Title", "Grant No",
    "Contract Award", "Project:", "Country:",
]
_WB_PRICE_RX = re.compile(
    r"(?:Signed Contract price|Evaluated Bid Price|Awarded Price|Contract Price|Bid Price at Opening)"
    r"\s*[:\s]\s*([A-Z]{3}|US\$|USD|\$)\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)


def _wb_grab(plain: str, label: str) -> str:
    stops_alt = "|".join(re.escape(s) for s in _WB_STOP_LABELS if s != label)
    pat = rf"{re.escape(label)}\s*:?\s*(.+?)(?=\s+(?:{stops_alt})\s*[:\s]|$)"
    m = re.search(pat, plain, re.IGNORECASE)
    return m.group(1).strip()[:300] if m else ""


def wb_extract_details(raw_html: str) -> dict:
    if not raw_html:
        return {}
    plain = re.sub(r"\s+", " ", clean_html(raw_html)).strip()
    details = {}
    for key, label in [
        ("scope", "Scope of Contract"),
        ("procurement_method", "Procurement Method"),
        ("duration", "Duration of Contract"),
        ("reference_no", "Bid/Contract Reference No"),
        ("loan_credit", "Loan/Credit/TF Info"),
        ("awarded_bidder", "Awarded Bidder(s)"),
        ("contract_title", "Contract Title"),
    ]:
        val = _wb_grab(plain, label)
        if val:
            details[key] = val
    m = _WB_PRICE_RX.search(plain)
    if m:
        cur = m.group(1).upper().replace("US$", "USD").replace("$", "USD")
        formatted = _format_compact_money(cur, m.group(2), "")
        if formatted:
            details["contract_amount"] = formatted
    if plain:
        details["text_excerpt"] = plain[:1200]
    return details


def extract_notice_text(raw_data) -> Optional[str]:
    """raw_data 에서 공고 본문 발췌를 자동 추출 (수집기별 키 차이 흡수)."""
    if not isinstance(raw_data, dict):
        return None
    wb = raw_data.get("wb_details")
    if isinstance(wb, dict):
        for k in ("text_excerpt", "scope", "description"):
            v = wb.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()[:1500]
    for k in ("description", "Description", "bid_description", "scope",
              "summary", "project_summary", "content", "body"):
        v = raw_data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()[:1500]
    return None


# ── 국가명 → 좌표(텍스트 내 국가 탐지용) / ISO2 ─────────────────────────────
COUNTRY_COORDS = {
    "Afghanistan": (33.9, 67.7), "Albania": (41.2, 20.2), "Algeria": (28.0, 1.7),
    "Angola": (-11.2, 17.9), "Argentina": (-38.4, -63.6), "Armenia": (40.1, 45.0),
    "Azerbaijan": (40.1, 47.6), "Bangladesh": (23.7, 90.4), "Benin": (9.3, 2.3),
    "Bolivia": (-16.3, -63.6), "Bosnia and Herzegovina": (44.2, 17.7),
    "Burkina Faso": (12.4, -1.6), "Burundi": (-3.4, 29.9), "Cambodia": (12.6, 104.8),
    "Cameroon": (3.9, 11.5), "Central African Republic": (6.6, 20.9),
    "Chad": (15.5, 18.7), "Colombia": (4.6, -74.3), "Cote d'Ivoire": (7.5, -5.5),
    "Democratic Republic of Congo": (-4.0, 21.8), "Dominican Republic": (18.7, -70.2),
    "Ecuador": (-1.8, -78.2), "Egypt": (26.8, 30.8), "El Salvador": (13.8, -88.9),
    "Ethiopia": (9.1, 40.5), "Georgia": (42.3, 43.4), "Ghana": (7.9, -1.0),
    "Guatemala": (15.8, -90.2), "Guinea": (11.0, -10.9), "Haiti": (18.9, -72.3),
    "Honduras": (15.2, -86.2), "India": (20.6, 79.1), "Indonesia": (-0.8, 113.9),
    "Iraq": (33.2, 43.7), "Jordan": (30.6, 36.2), "Kazakhstan": (48.0, 66.9),
    "Kenya": (-0.0, 37.9), "Kyrgyzstan": (41.2, 74.8), "Laos": (18.2, 103.9),
    "Lebanon": (33.9, 35.9), "Liberia": (6.4, -9.4), "Libya": (27.0, 17.2),
    "Madagascar": (-18.8, 47.0), "Malawi": (-13.3, 34.3), "Mali": (17.6, -2.0),
    "Mauritania": (21.0, -10.9), "Mexico": (23.6, -102.6), "Moldova": (47.4, 28.4),
    "Mongolia": (46.9, 103.8), "Morocco": (31.8, -7.1), "Mozambique": (-18.7, 35.5),
    "Myanmar": (21.9, 95.9), "Nepal": (28.4, 84.1), "Nicaragua": (12.9, -85.2),
    "Niger": (17.6, 8.1), "Nigeria": (9.1, 8.7), "Oman": (21.5, 55.9),
    "Pakistan": (30.4, 69.3), "Panama": (8.5, -80.8), "Papua New Guinea": (-6.3, 143.9),
    "Paraguay": (-23.4, -58.4), "Peru": (-9.2, -75.0), "Philippines": (12.9, 121.8),
    "Rwanda": (-2.0, 29.9), "Saudi Arabia": (23.9, 45.1), "Senegal": (14.5, -14.5),
    "Sierra Leone": (8.5, -11.8), "Somalia": (6.2, 46.2), "South Sudan": (7.9, 29.6),
    "Sri Lanka": (7.9, 80.8), "Sudan": (12.9, 30.2), "Suriname": (3.9, -56.0),
    "Tajikistan": (38.9, 71.3), "Tanzania": (-6.4, 34.9), "Togo": (8.6, 0.8),
    "Tunisia": (34.0, 9.0), "Türkiye": (38.9, 35.2), "Turkey": (38.9, 35.2),
    "Turkmenistan": (38.9, 59.6), "Uganda": (1.4, 32.3), "Ukraine": (48.4, 31.2),
    "Uzbekistan": (41.4, 64.6), "Venezuela": (6.4, -66.6), "Vietnam": (14.1, 108.3),
    "Yemen": (15.6, 48.5), "Zambia": (-13.1, 27.8), "Zimbabwe": (-20.0, 30.0),
    "West Africa": (12.0, -3.0), "East Africa": (1.0, 38.0),
    "Southern Africa": (-20.0, 25.0), "Sub-Saharan Africa": (5.0, 20.0),
    "South Asia": (23.0, 77.0), "Southeast Asia": (10.0, 106.0),
    "Central Asia": (42.0, 63.0),
}

_COUNTRY_ISO2 = {
    "Afghanistan": "AF", "Albania": "AL", "Algeria": "DZ", "Angola": "AO",
    "Argentina": "AR", "Armenia": "AM", "Azerbaijan": "AZ", "Bangladesh": "BD",
    "Benin": "BJ", "Bolivia": "BO", "Bosnia and Herzegovina": "BA",
    "Burkina Faso": "BF", "Burundi": "BI", "Cambodia": "KH", "Cameroon": "CM",
    "Central African Republic": "CF", "Chad": "TD", "Colombia": "CO",
    "Cote d'Ivoire": "CI", "Democratic Republic of Congo": "CD",
    "Dominican Republic": "DO", "Ecuador": "EC", "Egypt": "EG", "El Salvador": "SV",
    "Ethiopia": "ET", "Georgia": "GE", "Ghana": "GH", "Guatemala": "GT",
    "Guinea": "GN", "Haiti": "HT", "Honduras": "HN", "India": "IN",
    "Indonesia": "ID", "Iraq": "IQ", "Jordan": "JO", "Kazakhstan": "KZ",
    "Kenya": "KE", "Kyrgyzstan": "KG", "Laos": "LA", "Lebanon": "LB",
    "Liberia": "LR", "Libya": "LY", "Madagascar": "MG", "Malawi": "MW",
    "Mali": "ML", "Mauritania": "MR", "Mexico": "MX", "Moldova": "MD",
    "Mongolia": "MN", "Morocco": "MA", "Mozambique": "MZ", "Myanmar": "MM",
    "Nepal": "NP", "Nicaragua": "NI", "Niger": "NE", "Nigeria": "NG", "Oman": "OM",
    "Pakistan": "PK", "Panama": "PA", "Papua New Guinea": "PG", "Paraguay": "PY",
    "Peru": "PE", "Philippines": "PH", "Rwanda": "RW", "Saudi Arabia": "SA",
    "Senegal": "SN", "Sierra Leone": "SL", "Somalia": "SO", "South Sudan": "SS",
    "Sri Lanka": "LK", "Sudan": "SD", "Suriname": "SR", "Tajikistan": "TJ",
    "Tanzania": "TZ", "Togo": "TG", "Tunisia": "TN", "Türkiye": "TR",
    "Turkey": "TR", "Turkmenistan": "TM", "Uganda": "UG", "Ukraine": "UA",
    "Uzbekistan": "UZ", "Venezuela": "VE", "Vietnam": "VN", "Yemen": "YE",
    "Zambia": "ZM", "Zimbabwe": "ZW",
}


def country_iso2(country: Optional[str]) -> Optional[str]:
    if not country:
        return None
    if country in _COUNTRY_ISO2:
        return _COUNTRY_ISO2[country]
    first = country.split()[0]
    for name, iso in _COUNTRY_ISO2.items():
        if name.startswith(first):
            return iso
    return None


# ── KRC dict → normalize() 변환 ──────────────────────────────────────────────
_SOURCE_MAP = {"worldbank": "wb"}  # 발주공고 schema enum 에 맞춤
_KO_SOURCES = {"koica", "edcf"}


def _build_raw_text(d: dict) -> Optional[str]:
    parts = []
    body = extract_notice_text(d.get("raw_data"))
    if body:
        parts.append(body)
    meta = " · ".join(
        str(x) for x in (d.get("client"), d.get("region"),
                         d.get("procurement_category"), d.get("project_name"))
        if x and str(x) != (d.get("title") or "")
    )
    if meta:
        parts.append(meta)
    text = "\n".join(parts).strip()
    return text or None


def to_normalized(d: dict) -> dict:
    """KRC 스타일 수집 dict → normalize.normalize() 출력(notices 행)."""
    src = _SOURCE_MAP.get(d["source"], d["source"])
    budget_amount, budget_currency = parse_amount(d.get("contract_value") or "")
    source_url = d.get("source_url") or ""
    source_id = d.get("source_id") or hashlib.md5(
        f"{src}|{source_url}|{d.get('title','')}".encode("utf-8")
    ).hexdigest()[:20]
    country = (d.get("country") or "").strip() or None
    return normalize.normalize(
        source=src,
        source_notice_id=source_id,
        title=d.get("title") or "",
        source_url=source_url,
        country=country,
        country_iso=country_iso2(country),
        sector=d.get("sector"),
        notice_type=d.get("notice_type") or None,
        procurement_method=d.get("procurement_method") or None,
        published_at=to_iso_date(d.get("posted_date")),
        deadline_at=to_iso_date(d.get("deadline")),
        budget_amount=budget_amount,
        budget_currency=budget_currency,
        raw_text=_build_raw_text(d),
        language="ko" if src in _KO_SOURCES else "en",
    )
