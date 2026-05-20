"""
KRC World Market — 공개 API
인증 없이 접근 가능. 농업분야(sector=agriculture 또는 krc_tags에 '농업'/'수자원' 포함) 공고만 노출.
"""
from flask import Blueprint, request, jsonify
from sqlalchemy import func, or_
from models import db, BidNotice, ScrapingRun

public_bp = Blueprint('public', __name__)


AGRI_TAGS = ['농업', '수자원']


def _agri_filter():
    """농업분야 잠금 필터 — sector='agriculture' OR krc_tags ⊇ {농업|수자원}."""
    conds = [BidNotice.sector == 'agriculture']
    for tag in AGRI_TAGS:
        conds.append(BidNotice.krc_tags.contains([tag]))
    return or_(*conds)


@public_bp.route('/notices', methods=['GET'])
def get_notices():
    """공고 목록 — 농업분야 전용.

    Query params:
      source      — worldbank, adb, afdb, aiib, isdb, koica, edcf, ungm (복수: 쉼표구분)
      country     — 국가명 (부분일치)
      search      — 제목/국가/분야 검색
      tags        — KRC 태그 (쉼표구분) — 농업/수자원/기후복원력/인프라/컨설팅
      status      — deadline status: open, urgent, closed
      page        — 페이지 번호 (1-based)
      perPage     — 페이지당 건수 (기본 50, 최대 200)
      sort        — relevance(기본) | deadline | posted | created
    """
    source_param = request.args.get('source', '')
    country_param = request.args.get('country', '')
    search_param = request.args.get('search', '')
    tags_param = request.args.get('tags', '')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('perPage', 50, type=int)), 200)
    sort_param = request.args.get('sort', 'relevance')

    query = BidNotice.query.filter(_agri_filter())

    if source_param:
        sources = [s.strip() for s in source_param.split(',') if s.strip()]
        if sources:
            query = query.filter(BidNotice.source.in_(sources))

    if country_param:
        query = query.filter(BidNotice.country.ilike(f'%{country_param}%'))

    if search_param:
        like = f'%{search_param}%'
        query = query.filter(
            BidNotice.title.ilike(like) |
            BidNotice.title_ko.ilike(like) |
            BidNotice.country.ilike(like) |
            BidNotice.sector.ilike(like) |
            BidNotice.project_name.ilike(like)
        )

    if tags_param:
        tags = [t.strip() for t in tags_param.split(',') if t.strip()]
        for tag in tags:
            query = query.filter(BidNotice.krc_tags.contains([tag]))

    # 정렬
    if sort_param == 'deadline':
        query = query.order_by(
            BidNotice.deadline_date.asc().nullslast(),
            BidNotice.created_at.desc(),
        )
    elif sort_param == 'posted':
        query = query.order_by(
            BidNotice.posted_date.desc().nullslast(),
            BidNotice.created_at.desc(),
        )
    elif sort_param == 'created':
        query = query.order_by(BidNotice.created_at.desc())
    else:  # relevance (default)
        query = query.order_by(
            BidNotice.relevance_score.desc(),
            BidNotice.created_at.desc(),
        )

    total = query.count()
    notices = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'success': True,
        'data': [n.to_public_dict() for n in notices],
        'pagination': {
            'page': page,
            'perPage': per_page,
            'total': total,
            'totalPages': (total + per_page - 1) // per_page if total else 0,
        },
    })


@public_bp.route('/notices/<int:notice_id>', methods=['GET'])
def get_notice(notice_id):
    """공고 상세 — 농업분야 항목만."""
    notice = BidNotice.query.filter(BidNotice.id == notice_id, _agri_filter()).first()
    if not notice:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return jsonify({'success': True, 'data': notice.to_public_dict()})


@public_bp.route('/stats', methods=['GET'])
def get_stats():
    """요약 통계 — 농업분야 공고 기준."""
    base = BidNotice.query.filter(_agri_filter())
    total = base.count()

    # 발주처별
    by_source = db.session.query(
        BidNotice.source, func.count(BidNotice.id)
    ).filter(_agri_filter()).group_by(BidNotice.source).all()

    # 국가별 (상위 15)
    by_country = db.session.query(
        BidNotice.country, func.count(BidNotice.id)
    ).filter(
        _agri_filter(),
        BidNotice.country.isnot(None),
        BidNotice.country != '',
    ).group_by(BidNotice.country).order_by(func.count(BidNotice.id).desc()).limit(15).all()

    # 분야별
    by_sector = db.session.query(
        BidNotice.sector, func.count(BidNotice.id)
    ).filter(
        _agri_filter(),
        BidNotice.sector.isnot(None),
    ).group_by(BidNotice.sector).all()

    # 마감 임박 (7일 이내)
    from datetime import date, timedelta
    today = date.today()
    urgent_count = base.filter(
        BidNotice.deadline_date.isnot(None),
        BidNotice.deadline_date >= today,
        BidNotice.deadline_date <= today + timedelta(days=7),
    ).count()

    # 최근 수집 이력
    last_run = ScrapingRun.query.order_by(ScrapingRun.run_at.desc()).first()

    return jsonify({
        'success': True,
        'total': total,
        'urgent': urgent_count,
        'by_source': {src: cnt for src, cnt in by_source},
        'by_country': [{'country': c, 'count': cnt} for c, cnt in by_country],
        'by_sector': {sec: cnt for sec, cnt in by_sector},
        'last_collected': last_run.run_at.isoformat() + 'Z' if last_run else None,
        'last_created': last_run.total_created if last_run else 0,
    })


@public_bp.route('/sources', methods=['GET'])
def get_sources():
    """활성 발주처 목록 — 농업분야 공고 보유 기준."""
    from routes.collector import SOURCE_DISPLAY
    rows = db.session.query(
        BidNotice.source, func.count(BidNotice.id)
    ).filter(_agri_filter()).group_by(BidNotice.source).all()

    sources = [
        {
            'key': src,
            'name': SOURCE_DISPLAY.get(src, src.upper()),
            'count': cnt,
        }
        for src, cnt in sorted(rows, key=lambda x: -x[1])
    ]
    return jsonify({'success': True, 'data': sources})


@public_bp.route('/facets', methods=['GET'])
def get_facets():
    """필터 팩셋 — 국가·태그 선택지 반환 (농업분야 한정)."""
    countries = db.session.query(BidNotice.country).filter(
        _agri_filter(), BidNotice.country.isnot(None), BidNotice.country != ''
    ).distinct().all()

    sectors = db.session.query(BidNotice.sector).filter(
        _agri_filter(), BidNotice.sector.isnot(None)
    ).distinct().all()

    # KRC 태그 — JSON 배열에서 추출 (SQLite JSON 지원 제한으로 Python에서 집계)
    all_notices = BidNotice.query.filter(
        _agri_filter(), BidNotice.krc_tags.isnot(None)
    ).with_entities(BidNotice.krc_tags).all()
    tag_counts = {}
    for (tags,) in all_notices:
        if isinstance(tags, list):
            for t in tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1

    return jsonify({
        'success': True,
        'countries': sorted([c[0] for c in countries]),
        'sectors': sorted([s[0] for s in sectors if s[0]]),
        'krc_tags': [{'tag': t, 'count': c}
                     for t, c in sorted(tag_counts.items(), key=lambda x: -x[1])],
    })
