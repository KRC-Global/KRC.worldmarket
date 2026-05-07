"""
KRC World Market — 발주공고 수집 봇
World Bank / UNGM / ADB / AfDB / AIIB / IsDB / KOICA / EDCF
농업·수자원·인프라·컨설팅 관련 공고를 병렬 수집 → bid_notices 테이블 저장
"""
import os
import re
import hashlib
import threading
from datetime import datetime
from email.utils import parsedate_to_datetime
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from models import db, BidNotice, ScrapingRun

collector_bp = Blueprint('collector', __name__)

# ── 필터 키워드 ──────────────────────────────────────────────────────────────
AGRI_KEYWORDS = [
    'agriculture', 'agricultural', 'agri', 'farming', 'farm',
    'irrigation', 'rural', 'food security', 'food and agriculture',
    'crop', 'livestock', 'rice', 'grain', 'seed', 'fisheries',
    'forestry', 'water resource', 'drainage', 'land reclamation',
    'watershed', 'aquaculture', 'paddy', 'horticulture',
    'climate change', 'climate adaptation',
    'reservoir', 'dam', 'dams',
    'rehabilitation', 'refurbishment',
]

CONSULTING_KEYWORDS = [
    'consulting', 'consultancy', 'consultant', 'technical assistance',
    'advisory', 'supervision', 'feasibility', 'project management', 'pmc',
    'f/s', 'capacity building', 'assessment', 'planning',
    'engineering services', 'detailed design', 'design review',
    'design and supervision', 'preliminary design',
]

AGRI_KEYWORDS_KO = [
    '농업', '농촌', '관개', '식량', '작물', '수산', '산림', '농지',
    '용수', '양식', '축산', '수자원', '간척', '개간',
    '기후변화', '저수지', '댐', '개보수',
]

CONSULTING_KEYWORDS_KO = [
    '용역', '기술용역', '컨설팅', '자문', '기술협력', '타당성',
    '기술지원', '기술조사', '사업관리', '조사연구', '기본설계', '실시설계',
    'PMC', 'PMO', 'TA',
]

_AGRI_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(kw) for kw in AGRI_KEYWORDS) + r')(?:s|es)?\b',
    re.IGNORECASE,
)
_CONSULTING_RE = re.compile(
    r'\b(?:' + '|'.join(re.escape(kw) for kw in CONSULTING_KEYWORDS) + r')(?:s|es)?\b',
    re.IGNORECASE,
)

DEFAULT_FRESHNESS_DAYS = 60

# ── KRC 관련성 태깅 ──────────────────────────────────────────────────────────
KRC_TAGS_KEYWORDS = {
    '농업': (AGRI_KEYWORDS + AGRI_KEYWORDS_KO),
    '수자원': [
        'water', 'irrigation', 'drainage', 'dam', 'dams', 'flood', 'watershed',
        'hydrology', 'reservoir', 'pumping', 'canal',
        '수자원', '용수', '저수지', '댐', '관개', '홍수', '수문',
    ],
    '기후복원력': [
        'climate', 'climate change', 'climate adaptation', 'climate resilience',
        'disaster risk', 'drought', 'mangrove', 'coastal', 'adaptation',
        '기후변화', '기후', '재난', '가뭄',
    ],
    '인프라': [
        'civil works', 'construction', 'infrastructure', 'road', 'bridge',
        'pumping station', 'earthwork', 'embankment',
        '인프라', '공사', '시설',
    ],
    '컨설팅': (CONSULTING_KEYWORDS + CONSULTING_KEYWORDS_KO),
}


def compute_krc_relevance(title: str, sector: str = '',
                           project_name: str = '',
                           notice_type: str = '') -> tuple:
    """KRC 관련성 점수(0-100), 태그 리스트, 근거 문자열 반환."""
    text = ' '.join(filter(None, [title, sector, project_name, notice_type])).lower()
    matched_tags = []
    reasons = []
    for tag, keywords in KRC_TAGS_KEYWORDS.items():
        hits = [kw for kw in keywords if kw.lower() in text]
        if hits:
            matched_tags.append(tag)
            reasons.append(f"{tag}:{','.join(hits[:3])}")

    score = min(len(matched_tags) * 20, 80)
    # 컨설팅 서비스 추가 가중치
    if 'consulting services' in text or 'consultant' in text:
        score = min(score + 10, 100)
    # 농업+컨설팅 조합 최고 점수
    if '농업' in matched_tags and '컨설팅' in matched_tags:
        score = min(score + 10, 100)

    return score, matched_tags, '; '.join(reasons)


# ── 국가 좌표 사전 ────────────────────────────────────────────────────────────
COUNTRY_COORDS = {
    'Afghanistan': (33.9, 67.7), 'Albania': (41.2, 20.2),
    'Algeria': (28.0, 1.7), 'Angola': (-11.2, 17.9),
    'Argentina': (-38.4, -63.6), 'Armenia': (40.1, 45.0),
    'Azerbaijan': (40.1, 47.6), 'Bangladesh': (23.7, 90.4),
    'Benin': (9.3, 2.3), 'Bolivia': (-16.3, -63.6),
    'Bosnia and Herzegovina': (44.2, 17.7), 'Burkina Faso': (12.4, -1.6),
    'Burundi': (-3.4, 29.9), 'Cambodia': (12.6, 104.8),
    'Cameroon': (3.9, 11.5), 'Central African Republic': (6.6, 20.9),
    'Chad': (15.5, 18.7), 'Colombia': (4.6, -74.3),
    "Cote d'Ivoire": (7.5, -5.5), 'Democratic Republic of Congo': (-4.0, 21.8),
    'Dominican Republic': (18.7, -70.2), 'Ecuador': (-1.8, -78.2),
    'Egypt': (26.8, 30.8), 'El Salvador': (13.8, -88.9),
    'Ethiopia': (9.1, 40.5), 'Georgia': (42.3, 43.4),
    'Ghana': (7.9, -1.0), 'Guatemala': (15.8, -90.2),
    'Guinea': (11.0, -10.9), 'Haiti': (18.9, -72.3),
    'Honduras': (15.2, -86.2), 'India': (20.6, 79.1),
    'Indonesia': (-0.8, 113.9), 'Iraq': (33.2, 43.7),
    'Jordan': (30.6, 36.2), 'Kazakhstan': (48.0, 66.9),
    'Kenya': (-0.0, 37.9), 'Kyrgyzstan': (41.2, 74.8),
    'Laos': (18.2, 103.9), 'Lebanon': (33.9, 35.9),
    'Liberia': (6.4, -9.4), 'Libya': (27.0, 17.2),
    'Madagascar': (-18.8, 47.0), 'Malawi': (-13.3, 34.3),
    'Mali': (17.6, -2.0), 'Mauritania': (21.0, -10.9),
    'Mexico': (23.6, -102.6), 'Moldova': (47.4, 28.4),
    'Mongolia': (46.9, 103.8), 'Morocco': (31.8, -7.1),
    'Mozambique': (-18.7, 35.5), 'Myanmar': (21.9, 95.9),
    'Nepal': (28.4, 84.1), 'Nicaragua': (12.9, -85.2),
    'Niger': (17.6, 8.1), 'Nigeria': (9.1, 8.7),
    'Oman': (21.5, 55.9), 'Pakistan': (30.4, 69.3),
    'Panama': (8.5, -80.8), 'Papua New Guinea': (-6.3, 143.9),
    'Paraguay': (-23.4, -58.4), 'Peru': (-9.2, -75.0),
    'Philippines': (12.9, 121.8), 'Rwanda': (-2.0, 29.9),
    'Saudi Arabia': (23.9, 45.1), 'Senegal': (14.5, -14.5),
    'Sierra Leone': (8.5, -11.8), 'Somalia': (6.2, 46.2),
    'South Sudan': (7.9, 29.6), 'Sri Lanka': (7.9, 80.8),
    'Sudan': (12.9, 30.2), 'Suriname': (3.9, -56.0),
    'Tajikistan': (38.9, 71.3), 'Tanzania': (-6.4, 34.9),
    'Togo': (8.6, 0.8), 'Tunisia': (34.0, 9.0),
    'Türkiye': (38.9, 35.2), 'Turkey': (38.9, 35.2),
    'Turkmenistan': (38.9, 59.6), 'Uganda': (1.4, 32.3),
    'Ukraine': (48.4, 31.2), 'Uzbekistan': (41.4, 64.6),
    'Venezuela': (6.4, -66.6), 'Vietnam': (14.1, 108.3),
    'Yemen': (15.6, 48.5), 'Zambia': (-13.1, 27.8),
    'Zimbabwe': (-20.0, 30.0),
    # 자주 쓰이는 지역명 매핑
    'West Africa': (12.0, -3.0), 'East Africa': (1.0, 38.0),
    'Southern Africa': (-20.0, 25.0), 'Sub-Saharan Africa': (5.0, 20.0),
    'South Asia': (23.0, 77.0), 'Southeast Asia': (10.0, 106.0),
    'Central Asia': (42.0, 63.0),
}


def _get_coords(country: str) -> tuple:
    """국가명으로 (lat, lng) 반환. 없으면 (None, None)."""
    if not country:
        return None, None
    # 직접 매칭
    c = COUNTRY_COORDS.get(country)
    if c:
        return c
    # 부분 매칭 (첫 단어로 시도)
    first = country.split()[0] if country else ''
    for k, v in COUNTRY_COORDS.items():
        if first and k.startswith(first):
            return v
    return None, None


# ── 공통 유틸 ────────────────────────────────────────────────────────────────
def _is_agri(text: str) -> bool:
    return bool(_AGRI_RE.search(text or ''))


def _is_consulting(text: str) -> bool:
    return bool(_CONSULTING_RE.search(text or ''))


def _is_agri_ko(text: str) -> bool:
    return any(kw in (text or '') for kw in AGRI_KEYWORDS_KO)


def _is_consulting_ko(text: str) -> bool:
    return any(kw in (text or '') for kw in CONSULTING_KEYWORDS_KO)


_DATE_RX = re.compile(r'(\d{4})[-./\s년]\s*(\d{1,2})[-./\s월]\s*(\d{1,2})')


def _parse_date_any(s: str):
    """YYYY-MM-DD / ISO datetime / Month DD YYYY / RFC 822 → date. 실패 시 None."""
    if not s:
        return None
    raw = str(s).strip()
    try:
        iso = raw.replace('Z', '+00:00').split('T')[0]
        return datetime.fromisoformat(iso).date()
    except Exception:
        pass
    m = _DATE_RX.search(raw)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except Exception:
            pass
    for fmt in ('%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y'):
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


def _is_deadline_passed(deadline_str: str) -> bool:
    d = _parse_date_any(deadline_str)
    if not d:
        return False
    return d < datetime.utcnow().date()


def _is_stale_date(date_str: str, days: int = DEFAULT_FRESHNESS_DAYS) -> bool:
    if not date_str:
        return False
    d = _parse_date_any(date_str)
    if d is None:
        for fmt in ('%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y'):
            try:
                d = datetime.strptime(str(date_str).strip(), fmt).date()
                break
            except ValueError:
                continue
    if d is None:
        return False
    return (datetime.utcnow().date() - d).days > days


def _clean_html(text: str) -> str:
    if not text:
        return ''
    return re.sub(r'<[^>]+>', ' ', str(text))


def _browser_headers(referer: str = '') -> dict:
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/125.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
    }
    if referer:
        headers['Referer'] = referer
        headers['Sec-Fetch-Site'] = 'same-origin'
    return headers


def _decorate_title(title: str, notice_type: str) -> str:
    title = (title or '').strip()
    notice_type = (notice_type or '').strip()
    if not notice_type:
        return title
    tag = f'[{notice_type}]'
    if tag.lower() in title.lower():
        return title
    return f'{title} {tag}'


_CURRENCY_CODES = (
    'USD|US\\$|EUR|€|GBP|£|JPY|¥|CNY|RMB|KRW'
    r'|INR|IDR|PHP|THB|VND|MYR|SGD|HKD|TWD|PKR|BDT|LKR|NPR'
    r'|NGN|EGP|ZAR|KES|UGX|TZS|ETB|GHS|MAD|DZD|TND|XOF|XAF|MZN'
    r'|BRL|MXN|ARS|COP|CLP|PEN|AUD|NZD|CAD|CHF'
    r'|RUB|TRY|SAR|AED|QAR|KWD|OMR|BHD|KZT|KGS|UZS|TJS|AZN|GEL|LSL|BWP'
)
_VALUE_RX = re.compile(
    rf'({_CURRENCY_CODES})\s*([\d,\.]+)\s*(million|billion|mln|bn|M|B|K)?',
    re.IGNORECASE,
)
_VALUE_LABELED_RX = re.compile(
    rf'(?:Total\s+(?:Project\s+)?Cost|Contract\s+(?:Price|Value|Amount)|'
    rf'Estimated\s+(?:Cost|Value|Budget|Amount)|Loan\s+Amount|'
    rf'Project\s+(?:Budget|Cost)|Budget\s+Amount)'
    rf'[^\d\n]{{0,30}}?({_CURRENCY_CODES})\s*([\d,]+(?:\.\d+)?)\s*'
    rf'(million|billion|mln|bn|M|B|K)?',
    re.IGNORECASE,
)
_MIN_CONTRACT_USD_THRESHOLD = 10_000


def _format_compact_money(currency: str, raw_amount: str, unit: str = '',
                           min_threshold: float = 0) -> str:
    try:
        num = float(raw_amount.replace(',', ''))
    except (TypeError, ValueError):
        return ''
    unit_lower = (unit or '').lower()
    if unit_lower in ('billion', 'bn', 'b'):
        num *= 1_000_000_000
    elif unit_lower in ('million', 'mln', 'm'):
        num *= 1_000_000
    elif unit_lower in ('k',):
        num *= 1_000
    cur_raw = re.sub(r'(USD)+', 'USD',
                     (currency or '').upper().replace('US$', 'USD').replace('$', 'USD').replace('€', 'EUR').replace('£', 'GBP'))
    small_unit_currencies = {'IDR', 'VND', 'UZS', 'KRW', 'JPY', 'PKR', 'NGN',
                             'PHP', 'KGS', 'KZT', 'UGX', 'TZS', 'LKR', 'NPR', 'BDT', 'LSL'}
    threshold = min_threshold
    if cur_raw in small_unit_currencies and threshold:
        threshold = threshold * 10
    if threshold and num < threshold:
        return ''
    if num >= 1_000_000_000:
        amt = f'{num / 1_000_000_000:.1f}B'
    elif num >= 1_000_000:
        amt = f'{num / 1_000_000:.1f}M'
    elif num >= 1_000:
        amt = f'{num / 1_000:.1f}K'
    else:
        amt = f'{num:,.0f}'
    return f'{cur_raw} {amt}'.strip() if cur_raw else amt


def _extract_value_from_text(text: str) -> str:
    if not text:
        return ''
    clean = _clean_html(text)
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
    return ''


def _compact_currency_phrase(raw: str) -> str:
    if not raw:
        return ''
    parts = re.split(r'[\n;]+', raw.strip())
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
    return compact + (f' (외 {extra}건)' if extra > 0 else '')


def _parse_amount(contract_value: str) -> tuple:
    """'USD 2.3M' → (2300000.0, 'USD'). 실패 시 (None, None)."""
    if not contract_value:
        return None, None
    m = re.search(
        rf'({_CURRENCY_CODES})\s*([\d,\.]+)\s*(billion|million|mln|bn|B|M|K)?',
        contract_value, re.IGNORECASE,
    )
    if not m:
        return None, None
    cur = re.sub(r'(USD)+', 'USD',
                 m.group(1).upper().replace('US$', 'USD').replace('$', 'USD'))
    try:
        num = float(m.group(2).replace(',', ''))
    except ValueError:
        return None, None
    unit = (m.group(3) or '').lower()
    if unit in ('billion', 'bn', 'b'):
        num *= 1_000_000_000
    elif unit in ('million', 'mln', 'm'):
        num *= 1_000_000
    elif unit == 'k':
        num *= 1_000
    return num, cur


# ── 제목/국가 정규화 (중복 판정용) ──────────────────────────────────────────
_TITLE_NORMALIZE_RX = re.compile(r'[\s\W_]+', re.UNICODE)
_BRACKETED_RX = re.compile(r'[\[\(\{][^\]\)\}]*[\]\)\}]')
_NOTICE_TYPE_TOKENS_RX = re.compile(
    r'\b(?:request\s+for\s+(?:bids?|proposals?|expression\s+of\s+interest|'
    r'expressions?\s+of\s+interest|quotations?|eoi)|rfp|rfb|rfq|reoi|'
    r'general\s+procurement\s+notice|specific\s+procurement\s+notice|'
    r'gpn|spn|eoi|pqn|pre[- ]?qualification|addend(?:um|a)|amendment|'
    r'invitation\s+for\s+(?:bids?|tenders?)|ifb|ift|contract\s+award(?:\s+notice)?|'
    r'procurement\s+plan|notices?|early\s+market\s+engagement(?:\s+notice)?)\b',
    re.IGNORECASE,
)


def _normalize_title(title: str) -> str:
    if not title:
        return ''
    t = title.lower()
    t = _BRACKETED_RX.sub(' ', t)
    t = _NOTICE_TYPE_TOKENS_RX.sub(' ', t)
    t = _TITLE_NORMALIZE_RX.sub('', t)
    return t[:120]


def _normalize_country(country: str) -> str:
    if not country:
        return ''
    return _TITLE_NORMALIZE_RX.sub('', country.lower())[:50]


# ── 핑거프린트 캐시 (매 수집 배치 1회 빌드) ─────────────────────────────────
_existing_fingerprints_cache = None


def _build_fingerprint_cache():
    global _existing_fingerprints_cache
    cache = set()
    url_set = set()
    source_id_set = set()
    for n in BidNotice.query.all():
        if n.source_url:
            url_set.add(n.source_url)
        if n.source and n.source_id:
            source_id_set.add((n.source, n.source_id))
        tn = _normalize_title(n.title or '')
        cn = _normalize_country(n.country or '')
        if tn:
            cache.add((tn, cn))
    _existing_fingerprints_cache = (cache, url_set, source_id_set)


# ── WB notice_text 파서 ──────────────────────────────────────────────────────
_WB_STOP_LABELS = [
    'Scope of Contract', 'Notice Version No', 'Procurement Method',
    'Loan/Credit/TF Info', 'Awarded Bidder(s)', 'Duration of Contract',
    'Bid/Contract Reference No', 'Contract Title', 'Grant No',
    'Contract Award', 'Project:', 'Country:',
]
_WB_PRICE_RX = re.compile(
    r'(?:Signed Contract price|Evaluated Bid Price|Awarded Price|Contract Price|Bid Price at Opening)'
    r'\s*[:\s]\s*([A-Z]{3}|US\$|USD|\$)\s*([\d,]+(?:\.\d+)?)',
    re.IGNORECASE,
)


def _wb_grab(plain: str, label: str) -> str:
    stops_alt = '|'.join(re.escape(s) for s in _WB_STOP_LABELS if s != label)
    pat = rf'{re.escape(label)}\s*:?\s*(.+?)(?=\s+(?:{stops_alt})\s*[:\s]|$)'
    m = re.search(pat, plain, re.IGNORECASE)
    return m.group(1).strip()[:300] if m else ''


def _wb_extract_details(raw_html: str) -> dict:
    if not raw_html:
        return {}
    plain = re.sub(r'\s+', ' ', _clean_html(raw_html)).strip()
    details = {}
    for key, label in [
        ('scope', 'Scope of Contract'),
        ('procurement_method', 'Procurement Method'),
        ('duration', 'Duration of Contract'),
        ('reference_no', 'Bid/Contract Reference No'),
        ('loan_credit', 'Loan/Credit/TF Info'),
        ('awarded_bidder', 'Awarded Bidder(s)'),
        ('contract_title', 'Contract Title'),
    ]:
        val = _wb_grab(plain, label)
        if val:
            details[key] = val
    m = _WB_PRICE_RX.search(plain)
    if m:
        cur = m.group(1).upper().replace('US$', 'USD').replace('$', 'USD')
        formatted = _format_compact_money(cur, m.group(2), '')
        if formatted:
            details['contract_amount'] = formatted
    if plain:
        details['text_excerpt'] = plain[:1200]
    return details


# ── _save_notice ─────────────────────────────────────────────────────────────
def _save_notice(source, title, country, client, sector,
                 contract_value, deadline, source_url, raw_data,
                 source_id=None, notice_type=None, procurement_method=None,
                 procurement_category=None, project_id=None, project_name=None,
                 posted_date=None, region=None) -> bool:
    """중복 확인 후 BidNotice 저장. 신규면 True, 중복이면 False.

    - source_id 가 있으면 (source, source_id) 기준 중복 체크 우선
    - 없으면 URL + (title_norm, country_norm) 기준
    - admin_status='review' 로 저장 (관리자 승인 후 공개)
    """
    global _existing_fingerprints_cache
    if not source_url or not title:
        return False

    if _existing_fingerprints_cache is None:
        _build_fingerprint_cache()

    fp_cache, url_cache, source_id_cache = _existing_fingerprints_cache

    # source_id 우선 중복 체크
    if source_id and (source, source_id) in source_id_cache:
        return False

    # URL 중복 체크
    if source_url in url_cache:
        return False

    # 제목+국가 중복 체크
    norm_title = _normalize_title(title)
    norm_country = _normalize_country(country or '')
    if norm_title and (norm_title, norm_country) in fp_cache:
        return False

    # 캐시 업데이트
    url_cache.add(source_url)
    if source_id:
        source_id_cache.add((source, source_id))
    if norm_title:
        fp_cache.add((norm_title, norm_country))

    # 날짜 파싱
    deadline_date = _parse_date_any(deadline) if deadline else None
    posted_date_obj = _parse_date_any(posted_date) if posted_date else None

    # 금액 파싱
    amount_value, amount_currency = _parse_amount(contract_value)

    # 좌표
    lat, lng = _get_coords(country)

    # KRC 관련성 태깅
    relevance_score, krc_tags, relevance_reason = compute_krc_relevance(
        title=title,
        sector=sector or '',
        project_name=project_name or '',
        notice_type=notice_type or '',
    )

    # source_hash (제목 + URL 해시로 변경 감지용)
    hash_src = f'{title}|{source_url}|{deadline}'
    source_hash = hashlib.sha256(hash_src.encode('utf-8')).hexdigest()[:64]

    notice = BidNotice(
        source=source,
        source_id=source_id,
        source_url=source_url[:500],
        source_hash=source_hash,
        last_seen_at=datetime.utcnow(),
        title=title[:500],
        country=(country or '')[:200] or None,
        region=(region or '')[:100] or None,
        client=(client or '')[:200] or None,
        sector=(sector or '')[:200] or None,
        notice_type=(notice_type or '')[:150] or None,
        procurement_method=(procurement_method or '')[:200] or None,
        procurement_category=(procurement_category or '')[:100] or None,
        project_id=(project_id or '')[:100] or None,
        project_name=project_name,
        posted_date=posted_date_obj,
        deadline_date=deadline_date,
        deadline=(deadline or '')[:50] or None,
        amount_value=amount_value,
        amount_currency=(amount_currency or '')[:10] or None,
        contract_value=(contract_value or '')[:100] or None,
        krc_tags=krc_tags,
        relevance_score=relevance_score,
        relevance_reason=relevance_reason or None,
        lat=lat,
        lng=lng,
        admin_status='review',   # 관리자 승인 전까지 공개 API에 노출 안 됨
        status='new',
        raw_data=raw_data,
    )
    db.session.add(notice)
    return True


# ── Tier 1: World Bank API ───────────────────────────────────────────────────
def _collect_worldbank() -> list:
    """World Bank Procurement Notices JSON API — 인증 불필요."""
    import requests as req

    url = 'https://search.worldbank.org/api/procnotices'
    results = []
    offset = 0
    page_size = 100
    max_total = 500

    while offset < max_total:
        params = {
            'format': 'json',
            'apilang': 'en',
            'rows': page_size,
            'os': offset,
            'srt': 'submission_date',
            'strdesc': 'desc',
        }
        r = req.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        raw = data.get('procnotices') or []
        items = list(raw.values()) if isinstance(raw, dict) else raw
        if not items:
            break

        for item in items:
            title = (item.get('project_name') or item.get('bid_description') or '').strip()
            if not title:
                continue

            notice_type = (item.get('notice_type') or '').strip()
            if notice_type.lower() == 'contract award':
                continue

            bid_desc = item.get('bid_description') or ''
            combined = f"{title} {bid_desc}"
            if not _is_agri(combined):
                continue

            status = (item.get('notice_status') or '').lower()
            if status in ('closed', 'cancelled', 'canceled'):
                continue

            nid = (item.get('id') or '').strip()
            if not nid:
                continue
            source_url = f'https://projects.worldbank.org/en/projects-operations/procurement-detail/{nid}'

            deadline_raw = (item.get('submission_deadline_date')
                            or item.get('submission_date')
                            or item.get('noticedate') or '')
            deadline = deadline_raw[:10] if deadline_raw else ''

            if _is_deadline_passed(deadline):
                continue
            posted = (item.get('noticedate') or item.get('submission_date') or '')
            if _is_stale_date(posted, days=DEFAULT_FRESHNESS_DAYS):
                continue

            wb_details = _wb_extract_details(item.get('notice_text', ''))
            contract_value = (wb_details.get('contract_amount')
                              or _extract_value_from_text(item.get('notice_text', '')))

            if item.get('project_id'):
                wb_details['project_id'] = item['project_id']

            raw_light = {k: v for k, v in item.items() if k != 'notice_text'}
            raw_light['wb_details'] = wb_details

            region = (item.get('regionname') or '').strip()
            procurement_cat = (item.get('procurement_group_desc_exact') or '').strip()
            procurement_method = (wb_details.get('procurement_method') or
                                  item.get('procurement_method_name') or '').strip()

            results.append({
                'source': 'worldbank',
                'source_id': nid,
                'title': _decorate_title(title, notice_type),
                'country': (item.get('project_ctry_name') or '').strip(),
                'region': region,
                'client': (item.get('contact_organization') or '').strip() or 'World Bank',
                'sector': 'agriculture',
                'notice_type': notice_type,
                'procurement_method': procurement_method,
                'procurement_category': procurement_cat,
                'project_id': (item.get('project_id') or '').strip(),
                'project_name': title,
                'contract_value': contract_value,
                'deadline': deadline,
                'posted_date': posted[:10] if posted else None,
                'source_url': source_url,
                'raw_data': raw_light,
            })

        try:
            total = int(data.get('total') or 0)
        except (TypeError, ValueError):
            total = 0
        offset += len(items)
        if total and offset >= total:
            break

    return results


# ── Tier 1: UNGM Developer API ───────────────────────────────────────────────
def _collect_ungm() -> list:
    """UNGM developer.ungm.org API — UNGM_API_KEY 필수."""
    api_key = os.environ.get('UNGM_API_KEY', '')
    if not api_key:
        print('[UNGM] UNGM_API_KEY 미설정 — 수집 건너뜀.')
        return []

    try:
        import requests as req
    except ImportError:
        return []

    url = 'https://developer.ungm.org/api/v1/notices'
    headers = {'Authorization': f'Bearer {api_key}', 'Accept': 'application/json'}
    results = []
    page = 0
    page_size = 50

    while True:
        params = {
            'TenderStatusCode': 'AC',
            'DeadlineFrom': datetime.utcnow().strftime('%Y-%m-%d'),
            'Keywords': 'agriculture irrigation rural food consulting technical',
            'PageSize': page_size,
            'PageIndex': page,
        }
        try:
            r = req.get(url, headers=headers, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f'[UNGM-API] page {page} 오류: {e}')
            break

        items = data.get('Notices') or data.get('notices') or []
        if not items:
            break

        for item in items:
            title = (item.get('Title') or item.get('title') or '').strip()
            desc = item.get('Description') or item.get('description') or ''
            combined = f"{title} {desc}"
            if not _is_agri(combined) and not _is_consulting(combined):
                continue

            deadline = (item.get('Deadline') or item.get('deadline') or '')[:10]
            if _is_deadline_passed(deadline):
                continue

            published = (item.get('PublishedOn') or item.get('published_on') or '')
            if _is_stale_date(published, days=DEFAULT_FRESHNESS_DAYS):
                continue

            source_url = (item.get('Url') or item.get('url') or
                          item.get('NoticeUrl') or '').strip()
            if not source_url:
                continue

            notice_id = str(item.get('Id') or item.get('id') or '')
            country = (item.get('Country') or item.get('country') or '').strip()
            agency = (item.get('AgencyName') or item.get('agency_name') or 'UNGM').strip()
            notice_type = (item.get('NoticeType') or item.get('notice_type') or '').strip()

            results.append({
                'source': 'ungm',
                'source_id': notice_id,
                'title': _decorate_title(title, notice_type),
                'country': country,
                'client': agency,
                'sector': 'consulting' if _is_consulting(combined) and not _is_agri(combined) else 'agriculture',
                'notice_type': notice_type,
                'contract_value': _extract_value_from_text(desc),
                'deadline': deadline,
                'posted_date': published[:10] if published else None,
                'source_url': source_url,
                'raw_data': item,
            })

        page += 1
        if len(items) < page_size:
            break

    return results


# ── Tier 1: ADB / AfDB via UNGM HTML 검색 ───────────────────────────────────
_UNGM_AGENCY_IDS = {'adb': 85, 'afdb': 84}


def _collect_via_ungm(source_key: str) -> list:
    """ADB/AfDB — UNGM 공개 HTML 검색 경유."""
    try:
        import requests as req
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    agency_id = _UNGM_AGENCY_IDS.get(source_key)
    if not agency_id:
        return []

    results = []
    page = 1
    MAX_PAGES = 3
    source_display = {'adb': 'ADB', 'afdb': 'AfDB'}.get(source_key, source_key.upper())

    while page <= MAX_PAGES:
        search_url = 'https://www.ungm.org/Public/Notice/Search'
        payload = {
            'pageIndex': page,
            'pageSize': 15,
            'sortField': 'DatePublished',
            'sortOrder': 'desc',
            'UNSPSCCodes': '',
            'AgencyId': agency_id,
            'Keywords': '',
        }
        try:
            r = req.post(search_url, json=payload,
                         headers={**_browser_headers(referer='https://www.ungm.org/'),
                                  'Content-Type': 'application/json',
                                  'Accept': 'text/html, */*; q=0.01',
                                  'X-Requested-With': 'XMLHttpRequest'},
                         timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f'[{source_key}-UNGM] page {page} 오류: {e}')
            break

        soup = BeautifulSoup(r.text, 'html.parser')
        rows = soup.select('tr.tableRow')
        if not rows:
            break

        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 6:
                continue

            notice_id_el = row.get('id', '') or row.select_one('td:first-child')
            notice_id = row.get('data-noticeid', '')

            title_el = cells[1].select_one('a') or cells[1]
            title = title_el.get_text(strip=True)
            if not title:
                continue

            href = title_el.get('href', '') if hasattr(title_el, 'get') else ''
            source_url = ('https://www.ungm.org' + href) if href.startswith('/') else href
            if not source_url or not source_url.startswith('http'):
                source_url = f'https://www.ungm.org/Public/Notice/{notice_id}' if notice_id else ''
            if not source_url:
                continue

            deadline = cells[2].get_text(strip=True) if len(cells) > 2 else ''
            if _is_deadline_passed(deadline):
                continue

            posted_raw = cells[3].get_text(strip=True) if len(cells) > 3 else ''
            if _is_stale_date(posted_raw, days=DEFAULT_FRESHNESS_DAYS):
                continue

            agency = cells[4].get_text(strip=True) if len(cells) > 4 else source_display
            notice_type = cells[5].get_text(strip=True) if len(cells) > 5 else ''
            country = cells[7].get_text(strip=True) if len(cells) > 7 else ''
            if country == 'Multiple destinations':
                country = ''

            combined = f'{title} {notice_type}'
            if not _is_agri(combined) and not _is_consulting(combined):
                continue

            results.append({
                'source': source_key,
                'source_id': notice_id or None,
                'title': _decorate_title(title, notice_type),
                'country': country,
                'client': agency or source_display,
                'sector': 'consulting' if _is_consulting(combined) and not _is_agri(combined) else 'agriculture',
                'notice_type': notice_type,
                'contract_value': _extract_value_from_text(title),
                'deadline': deadline,
                'posted_date': posted_raw[:10] if posted_raw else None,
                'source_url': source_url,
                'raw_data': {'ungm_id': notice_id, 'title': title,
                             'notice_type': notice_type, 'posted': posted_raw, 'agency': agency},
            })

        if len(rows) < 15:
            break
        page += 1

    print(f'[{source_key}-UNGM] {len(results)}건 수집')
    return results


def _collect_adb() -> list:
    return _collect_via_ungm('adb')


def _collect_afdb() -> list:
    return _collect_via_ungm('afdb')


# ── Tier 2: AIIB ─────────────────────────────────────────────────────────────
def _collect_aiib() -> list:
    """AIIB — ppo-data-all.js 정적 배열 파싱."""
    try:
        import requests as req
    except ImportError:
        return []

    data_url = ('https://www.aiib.org/en/opportunities/business/'
                'project-procurement/_common/ppo-data-all.js')
    try:
        r = req.get(data_url, headers=_browser_headers(referer='https://www.aiib.org/'),
                    timeout=15)
        r.raise_for_status()
        text = r.text
    except Exception as e:
        raise RuntimeError(f'AIIB ppo-data 요청 실패: {e}') from e

    m = re.search(r'ppoData\s*=\s*\[(.*)\]\s*;?\s*$', text, re.DOTALL)
    if not m:
        m = re.search(r'ppoData\s*=\s*\[(.*?)\];', text, re.DOTALL)
    if not m:
        raise RuntimeError('AIIB ppoData 배열을 찾지 못함')

    results = []
    obj_rx = re.compile(r'\{([^{}]+)\}')
    field_rx = re.compile(r'(\w+)\s*:\s*"((?:[^"\\]|\\.)*)"')
    today = datetime.utcnow().date()

    for obj_match in obj_rx.finditer(m.group(1)):
        fields = {k: v for k, v in field_rx.findall(obj_match.group(1))}
        if not fields:
            continue
        if (fields.get('ct') or '').strip() == 'Contract Awards':
            continue

        project = (fields.get('pj') or '').strip()
        desc = (fields.get('ds') or '').strip()
        country = (fields.get('mb') or '').strip()
        sector_raw = (fields.get('st') or '').strip()
        notice_type = (fields.get('tp') or '').strip()
        posted = (fields.get('id') or '').strip()
        deadline = (fields.get('cd') or '').strip()
        price = (fields.get('pc') or '').strip()
        doc_path = (fields.get('dc') or '').strip()

        combined = f'{project} {desc} {sector_raw} {notice_type}'
        agri_hit = _is_agri(combined) or sector_raw.lower() in ('water', 'rural')
        cons_hit = _is_consulting(combined)
        if not agri_hit and not cons_hit:
            continue

        if _is_stale_date(posted, days=DEFAULT_FRESHNESS_DAYS):
            continue

        deadline_iso = ''
        if deadline:
            for fmt in ('%B %d, %Y', '%b %d, %Y'):
                try:
                    dd = datetime.strptime(deadline, fmt).date()
                    deadline_iso = dd.isoformat()
                    if dd < today:
                        deadline_iso = None
                    break
                except ValueError:
                    continue

        if deadline_iso is None:
            continue

        if doc_path:
            source_url = ('https://www.aiib.org' + doc_path
                          if doc_path.startswith('/') else doc_path)
        else:
            fp = hashlib.md5(f'{project}|{country}|{notice_type}|{posted}'.encode()).hexdigest()[:12]
            source_url = (f'https://www.aiib.org/en/opportunities/business/'
                          f'project-procurement/list.html#{fp}')

        title = project or desc[:200] or notice_type
        if not title:
            continue

        results.append({
            'source': 'aiib',
            'source_id': hashlib.md5(f'{project}|{country}|{posted}'.encode()).hexdigest()[:20],
            'title': _decorate_title(title, notice_type),
            'country': country,
            'client': 'AIIB',
            'sector': 'consulting' if cons_hit and not agri_hit else 'agriculture',
            'notice_type': notice_type,
            'contract_value': _compact_currency_phrase(price),
            'deadline': deadline_iso or '',
            'posted_date': posted[:10] if posted else None,
            'source_url': source_url,
            'raw_data': fields,
        })

    return results


# ── Tier 2: IsDB ─────────────────────────────────────────────────────────────
_ISDB_PAGES = [
    ('https://www.isdb.org/project-procurement/taxonomy/term/207', 'GPN'),
    ('https://www.isdb.org/project-procurement/taxonomy/term/210', 'SPN'),
    ('https://www.isdb.org/project-procurement/taxonomy/term/211', 'SPN'),
]


def _collect_isdb() -> list:
    """IsDB — taxonomy 카테고리 페이지에서 활성 공고 수집."""
    try:
        import requests as req
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    results = []
    seen = set()
    type_map = {'eoi': 'EOI', 'gpn': 'GPN', 'spn': 'SPN',
                'ca': 'Contract Award', 'pq': 'Pre-Qualification', 'pqn': 'Pre-Qualification'}

    for list_url, default_type in _ISDB_PAGES:
        try:
            r = req.get(list_url, headers=_browser_headers(referer='https://www.isdb.org/'),
                        timeout=20)
            r.raise_for_status()
        except Exception as e:
            print(f'[IsDB] {list_url} 오류: {e}')
            continue

        soup = BeautifulSoup(r.text, 'html.parser')
        anchors = soup.select('a[href*="/project-procurement/tenders/"]')

        for a in anchors:
            href = a.get('href', '')
            title = a.get_text(strip=True)
            if not title or not href:
                continue
            if href.startswith('/'):
                href = 'https://www.isdb.org' + href
            if href in seen:
                continue
            seen.add(href)

            current_year = datetime.utcnow().year
            ym = re.search(r'/tenders/(\d{4})/([a-z\-]+)/', href)
            notice_type = default_type
            if ym:
                url_year = int(ym.group(1))
                notice_type = type_map.get(ym.group(2).lower(), notice_type)
                if url_year < current_year - 1:
                    continue

            if notice_type == 'Contract Award':
                continue

            parent = a.find_parent(['article', 'div', 'li']) or a.parent
            row_text = parent.get_text(' ', strip=True) if parent else title
            if re.search(r'\b(Closed|Fermé)\b', row_text, re.IGNORECASE):
                continue

            combined = f'{title} {row_text}'
            if not _is_agri(combined):
                continue

            deadline = ''
            dm = re.search(r'(\d{4}-\d{2}-\d{2})', row_text)
            if dm:
                deadline = dm.group(1)
            if not deadline:
                dm2 = re.search(
                    r'(?:Closing|Deadline|Close)\s*(?:Date)?[:\s]*'
                    r'(\d{1,2}\s+\w+\s+\d{4}|\w+\s+\d{1,2},?\s*\d{4})',
                    row_text, re.IGNORECASE)
                if dm2:
                    d = _parse_date_any(dm2.group(1))
                    if d:
                        deadline = d.isoformat()
            if _is_deadline_passed(deadline):
                continue

            country = ''
            for kw in ('Bangladesh', 'Uganda', 'Togo', 'Benin', 'Mauritania',
                       'Guinea', 'Morocco', 'Kyrgyzstan', 'Uzbekistan',
                       'Tajikistan', 'Turkey', 'Türkiye', 'Pakistan',
                       'Indonesia', 'Jordan', 'Sierra Leone', 'Suriname',
                       'Azerbaijan', 'Saudi Arabia', 'Kazakhstan', 'Egypt',
                       'Nigeria', 'Senegal', 'Mali', 'Burkina Faso', 'Niger',
                       'Cameroon', 'Chad', 'Mozambique', 'Oman', 'Tanzania'):
                if kw in row_text or kw in title:
                    country = kw
                    break

            results.append({
                'source': 'isdb',
                'source_id': hashlib.md5(href.encode()).hexdigest()[:20],
                'title': _decorate_title(title, notice_type),
                'country': country,
                'client': 'IsDB',
                'sector': 'consulting' if _is_consulting(combined) and not _is_agri(combined) else 'agriculture',
                'notice_type': notice_type,
                'contract_value': _extract_value_from_text(row_text),
                'deadline': deadline,
                'source_url': href,
                'raw_data': {'title': title, 'url': href, 'type': notice_type},
            })

    return results


# ── Tier 2: KOICA ─────────────────────────────────────────────────────────────
def _collect_koica() -> list:
    """KOICA — API 키 있으면 data.go.kr, 없으면 nebid.koica.go.kr HTML 스크래핑."""
    service_key = os.environ.get('KOICA_API_KEY', '')
    try:
        import requests as req
    except ImportError:
        return []

    if service_key:
        results = []
        url = 'https://apis.data.go.kr/1390802/koica_bid/koicaBidList'
        params = {'serviceKey': service_key, 'pageNo': 1, 'numOfRows': 100, 'type': 'json'}
        try:
            r = req.get(url, params=params, timeout=12)
            r.raise_for_status()
            data = r.json()
            items = (data.get('response', {}).get('body', {})
                        .get('items', {}).get('item', []))
            if isinstance(items, dict):
                items = [items]
            for item in items:
                title = (item.get('bidNm') or item.get('title') or '').strip()
                combined = title + ' ' + str(item)
                if not _is_agri(combined) and not _is_consulting(combined):
                    continue
                status = (item.get('bidPblancSttusCode') or item.get('status') or '').strip()
                if status and not (status in ('01', '공고중', 'OPEN', 'ACTIVE') or '공고' in status):
                    continue
                deadline = (item.get('bidClseDt') or '')[:10]
                if _is_deadline_passed(deadline):
                    continue
                posted = (item.get('bidPblancDt') or item.get('postDt') or '')[:10]
                if _is_stale_date(posted, days=DEFAULT_FRESHNESS_DAYS):
                    continue
                source_url = item.get('bidUrl') or item.get('url') or ''
                bid_no = item.get('bidNo') or item.get('id') or ''
                if not source_url and bid_no:
                    source_url = f'https://www.koica.go.kr/koica_kr/bid/view/{bid_no}'
                if not source_url:
                    continue
                notice_type = (item.get('bidPblancKndNm') or item.get('bidKndNm') or '').strip()
                sector = 'consulting' if _is_consulting(combined) and not _is_agri(combined) else 'agriculture'
                results.append({
                    'source': 'koica',
                    'source_id': str(bid_no) if bid_no else None,
                    'title': _decorate_title(title, notice_type),
                    'country': (item.get('country') or '').strip(),
                    'client': 'KOICA',
                    'sector': sector,
                    'notice_type': notice_type,
                    'contract_value': (item.get('bidAmt') or '').strip(),
                    'deadline': deadline,
                    'posted_date': posted,
                    'source_url': source_url,
                    'raw_data': item,
                })
        except Exception as e:
            print(f'[KOICA-API] 오류: {e}')
        return results

    # HTML fallback — nebid.koica.go.kr
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    list_url = 'https://nebid.koica.go.kr/oep/bepb/beffatPblancList.do'
    results = []
    seen = set()

    try:
        r = req.get(list_url, headers=_browser_headers(referer='https://nebid.koica.go.kr/'),
                    timeout=20, verify=False)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        rows = soup.select('tr.row[onclick]') or soup.select('tbody tr[onclick]')
        print(f'[KOICA-nebid] rows: {len(rows)}')

        for row in rows:
            onclick = row.get('onclick', '')
            m = re.search(r"beffatPblancInfoDetailInqire\('([^']+)'\)", onclick)
            if not m:
                continue
            bid_no = m.group(1)
            detail_url = (f'https://nebid.koica.go.kr/oep/bepb/'
                          f'beffatPblancInfoDetailInqire.do?pblancNo={bid_no}')
            if detail_url in seen:
                continue
            seen.add(detail_url)

            cols = [c.get_text(' ', strip=True) for c in row.select('td')]
            if len(cols) < 6:
                continue

            bid_kind = cols[2]
            item_kind = cols[3]
            title_td = row.select_one('td.left_T, td[title]')
            title = (title_td.get('title') if title_td and title_td.get('title')
                     else (cols[4] if len(cols) > 4 else ''))
            if not title:
                continue

            period = cols[5] if len(cols) > 5 else ''
            deadline_match = re.findall(r'\d{4}-\d{2}-\d{2}', period)
            deadline = deadline_match[-1] if deadline_match else ''
            if _is_deadline_passed(deadline):
                continue

            posted = cols[-1] if cols else ''
            if _is_stale_date(posted, days=DEFAULT_FRESHNESS_DAYS):
                continue

            combined = f"{title} {bid_kind} {item_kind}"
            agri_hit = _is_agri(combined) or _is_agri_ko(combined)
            cons_hit = _is_consulting(combined) or _is_consulting_ko(combined) or item_kind == '용역'
            if not agri_hit and not cons_hit:
                continue

            results.append({
                'source': 'koica',
                'source_id': bid_no,
                'title': _decorate_title(title, bid_kind or item_kind),
                'country': '',
                'client': 'KOICA',
                'sector': 'consulting' if cons_hit and not agri_hit else 'agriculture',
                'notice_type': bid_kind,
                'contract_value': '',
                'deadline': deadline,
                'posted_date': posted[:10] if posted else None,
                'source_url': detail_url,
                'raw_data': {'bid_no': bid_no, 'title': title, 'bid_kind': bid_kind,
                             'item_kind': item_kind, 'period': period, 'posted': posted},
            })
    except Exception as e:
        print(f'[KOICA-nebid] 오류: {e}')

    return results


# ── Tier 2: EDCF ──────────────────────────────────────────────────────────────
def _collect_edcf() -> list:
    """EDCF — edcfkorea.go.kr AJAX 스크래핑.

    POST /fnct/popup/popupajax → {"boardtypeid":"162","currentpage":N} → HTML 응답
    boardtypeid=162: 입찰공고
    """
    try:
        import requests as req
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    base = 'https://www.edcfkorea.go.kr'
    ajax_url = f'{base}/fnct/popup/popupajax'
    list_page_url = f'{base}/fe/HPHFFE065M01'

    session = req.Session()
    # 먼저 목록 페이지 방문해 세션 쿠키 획득
    try:
        session.get(list_page_url,
                    headers=_browser_headers(referer='https://www.edcfkorea.go.kr/'),
                    timeout=15)
    except Exception:
        pass

    results = []
    seen = set()
    MAX_PAGES = 5

    for page in range(1, MAX_PAGES + 1):
        try:
            resp = session.post(
                ajax_url,
                json={'boardtypeid': '162', 'currentpage': page, 'searchword': ''},
                headers={
                    **_browser_headers(referer=list_page_url),
                    'Content-Type': 'application/json;charset=UTF-8',
                    'Accept': 'text/html, */*; q=0.01',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f'[EDCF] page {page} 오류: {e}')
            break

        soup = BeautifulSoup(resp.text, 'html.parser')

        # div#ajaxbody 또는 tbody 내 행들
        rows = soup.select('#ajaxbody tr, table tbody tr')
        if not rows:
            # 목록 형식이 다를 경우 — 전체 행 탐색
            rows = soup.find_all('tr')

        if not rows:
            break

        page_has_items = False
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 2:
                continue

            # 제목 링크 찾기
            title_el = (row.select_one('td.subject a')
                        or row.select_one('td a[href*="boardid"]')
                        or row.select_one('td a'))
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title:
                continue

            # boardid 추출 (URL 또는 onclick에서)
            href = title_el.get('href', '')
            onclick = title_el.get('onclick', '')
            board_id_match = (re.search(r'boardid[=:]?\s*["\']?(\d+)', href)
                              or re.search(r'boardid[=:]?\s*["\']?(\d+)', onclick)
                              or re.search(r"['\"](\d{4,})['\"]", onclick))
            if board_id_match:
                board_id = board_id_match.group(1)
            else:
                # URL에서 마지막 숫자 시도
                nums = re.findall(r'\d{4,}', href + onclick)
                board_id = nums[-1] if nums else None

            if not board_id:
                continue

            source_url = (f'{base}/fe/HPHFFE066M01?boardtypeid=162&boardid={board_id}')
            if source_url in seen:
                continue
            seen.add(source_url)

            # 행에서 마감일 추출 — 셀 텍스트 순회
            deadline = ''
            country = ''
            row_text = row.get_text(' ', strip=True)

            # 날짜 패턴 (YYYY-MM-DD 또는 YYYY.MM.DD)
            date_matches = re.findall(r'\d{4}[-./]\d{1,2}[-./]\d{1,2}', row_text)
            if len(date_matches) >= 2:
                deadline = date_matches[-1].replace('.', '-').replace('/', '-')
            elif date_matches:
                deadline = date_matches[0].replace('.', '-').replace('/', '-')

            if _is_deadline_passed(deadline):
                continue

            # 간단한 국가 추출 (셀에서 발견 시)
            for cell in cells:
                cell_text = cell.get_text(strip=True)
                for kw in COUNTRY_COORDS.keys():
                    if kw in cell_text and len(kw) > 4:
                        country = kw
                        break
                if country:
                    break

            # 키워드 필터 — EDCF는 인프라/농업 모두 수집 (KRC 관련성 높음)
            combined = title + ' ' + row_text
            agri_hit = _is_agri(combined) or _is_agri_ko(combined)
            cons_hit = _is_consulting(combined) or _is_consulting_ko(combined)
            infra_hit = bool(re.search(r'\b(?:인프라|공사|건설|construction|infrastructure)\b',
                                       combined, re.IGNORECASE))
            if not agri_hit and not cons_hit and not infra_hit:
                continue

            page_has_items = True
            results.append({
                'source': 'edcf',
                'source_id': f'edcf_{board_id}',
                'title': title,
                'country': country,
                'client': 'EDCF',
                'sector': 'consulting' if cons_hit and not agri_hit else 'agriculture',
                'notice_type': 'Procurement Notice',
                'contract_value': _extract_value_from_text(row_text),
                'deadline': deadline,
                'source_url': source_url,
                'raw_data': {'board_id': board_id, 'title': title, 'row_text': row_text[:500]},
            })

        if not page_has_items:
            break

    print(f'[EDCF] {len(results)}건 수집')
    return results


# ── 수집기 등록 ───────────────────────────────────────────────────────────────
COLLECTORS = {
    'worldbank': _collect_worldbank,
    'ungm':      _collect_ungm,
    'adb':       _collect_adb,
    'afdb':      _collect_afdb,
    'aiib':      _collect_aiib,
    'isdb':      _collect_isdb,
    'koica':     _collect_koica,
    'edcf':      _collect_edcf,
}

SOURCE_DISPLAY = {
    'worldbank': 'World Bank',
    'ungm':      'UNGM',
    'adb':       'ADB',
    'afdb':      'AfDB',
    'aiib':      'AIIB',
    'isdb':      'IsDB',
    'koica':     'KOICA',
    'edcf':      'EDCF',
}


def _run_all_collectors(sources: list = None) -> tuple:
    """지정된 수집기를 ThreadPoolExecutor 로 병렬 실행."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import traceback

    target = {k: v for k, v in COLLECTORS.items()
              if not sources or k in sources}
    all_items = []
    errors = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_name = {executor.submit(fn): name for name, fn in target.items()}
        for future in as_completed(future_to_name, timeout=120):
            name = future_to_name[future]
            try:
                items = future.result()
                all_items.extend(items)
                print(f'[collector] {name}: {len(items)}건')
            except Exception as e:
                errors[name] = str(e)
                print(f'[collector] {name}: FAILED — {e}')
                traceback.print_exc()

    return all_items, errors


def _do_collect(sources: list = None, trigger: str = 'manual') -> dict:
    """실제 수집 작업 수행 후 결과 dict 반환."""
    global _existing_fingerprints_cache
    _existing_fingerprints_cache = None

    all_items, errors = _run_all_collectors(sources)

    # 배치 내 선제 중복 제거
    _build_fingerprint_cache()
    deduped = []
    seen_urls = set()
    seen_fp = set()
    for it in all_items:
        url = it.get('source_url', '')
        fp = (_normalize_title(it.get('title', '')),
              _normalize_country(it.get('country', '')))
        if url and url in seen_urls:
            continue
        if fp[0] and fp in seen_fp:
            continue
        seen_urls.add(url)
        if fp[0]:
            seen_fp.add(fp)
        deduped.append(it)
    all_items = deduped

    created = 0
    skipped = 0
    created_by_source = {}
    updated = 0

    for item in all_items:
        src = item['source']
        saved = _save_notice(
            source=src,
            title=item['title'],
            country=item.get('country', ''),
            client=item.get('client', ''),
            sector=item.get('sector', ''),
            contract_value=item.get('contract_value', ''),
            deadline=item.get('deadline', ''),
            source_url=item['source_url'],
            raw_data=item.get('raw_data'),
            source_id=item.get('source_id'),
            notice_type=item.get('notice_type'),
            procurement_method=item.get('procurement_method'),
            procurement_category=item.get('procurement_category'),
            project_id=item.get('project_id'),
            project_name=item.get('project_name'),
            posted_date=item.get('posted_date'),
            region=item.get('region'),
        )
        if saved:
            created += 1
            created_by_source[src] = created_by_source.get(src, 0) + 1
        else:
            skipped += 1

    sources_summary = [
        {
            'name': SOURCE_DISPLAY.get(k, k),
            'count': sum(1 for it in all_items if it['source'] == k),
            'created': created_by_source.get(k, 0),
            'error': errors.get(k),
        }
        for k in COLLECTORS.keys()
        if not sources or k in sources
    ]
    run = ScrapingRun(
        trigger=trigger,
        total_found=len(all_items),
        total_created=created,
        total_updated=updated,
        total_skipped=skipped,
        sources=sources_summary,
    )
    db.session.add(run)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return {'success': False, 'error': f'DB 저장 실패: {e}'}

    return {
        'success': True,
        'created': created,
        'skipped': skipped,
        'updated': updated,
        'total_fetched': len(all_items),
        'by_source': created_by_source,
        'errors': errors,
        'sources': sources_summary,
        'collected_at': datetime.utcnow().isoformat() + 'Z',
    }


# ── 인증 데코레이터 ──────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = (request.headers.get('X-Admin-Key')
               or request.args.get('key', ''))
        admin_key = current_app.config.get('ADMIN_KEY', '')
        if not admin_key or key != admin_key:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ── 엔드포인트 ────────────────────────────────────────────────────────────────
@collector_bp.route('/collect', methods=['POST'])
@admin_required
def collect_endpoint():
    """수동 수집 트리거.
    Body (JSON, optional): {"sources": ["worldbank", "adb"], "trigger": "manual"}
    """
    body = request.get_json(silent=True) or {}
    sources = body.get('sources') or None
    trigger = (body.get('trigger') or request.args.get('trigger') or 'manual')[:20]

    if sources:
        invalid = [s for s in sources if s not in COLLECTORS]
        if invalid:
            return jsonify({'success': False, 'error': f'알 수 없는 소스: {invalid}'}), 400

    try:
        result = _do_collect(sources=sources, trigger=trigger)
        return jsonify(result), (200 if result.get('success') else 500)
    except Exception as e:
        import traceback; traceback.print_exc()
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@collector_bp.route('/runs', methods=['GET'])
@admin_required
def get_runs():
    """수집 이력 조회."""
    limit = min(int(request.args.get('limit', 20)), 100)
    runs = (ScrapingRun.query.order_by(ScrapingRun.run_at.desc())
            .limit(limit).all())
    return jsonify({'success': True, 'data': [r.to_dict() for r in runs]})


@collector_bp.route('/cleanup', methods=['POST'])
@admin_required
def cleanup_endpoint():
    """마감/오래된 공고 삭제."""
    try:
        days = int(request.args.get('days', DEFAULT_FRESHNESS_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_FRESHNESS_DAYS
    days = max(1, min(days, 365))

    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    # 마감된 공고
    expired = BidNotice.query.filter(
        BidNotice.deadline_date.isnot(None),
        BidNotice.deadline_date < datetime.utcnow().date(),
    ).all()
    expired_ids = [n.id for n in expired]

    # 오래된 공고
    old_ids = [n.id for n in BidNotice.query.filter(BidNotice.created_at < cutoff).all()]

    all_ids = list(set(expired_ids + old_ids))
    deleted = 0
    if all_ids:
        try:
            deleted = BidNotice.query.filter(BidNotice.id.in_(all_ids)).delete(synchronize_session=False)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({
        'success': True,
        'deleted': deleted,
        'expired_count': len(expired_ids),
        'old_count': len(old_ids),
        'days': days,
    })
