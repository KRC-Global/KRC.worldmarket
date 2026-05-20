"""
KRC World Market — 관리자 API
Supabase JWT (Authorization: Bearer) 또는 X-Admin-Key 헤더로 인증.
"""
import csv
import io
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app, Response
from sqlalchemy import func
from models import db, BidNotice, ScrapingRun
from auth import admin_required

admin_bp = Blueprint('admin', __name__)


# ── 공고 목록 (관리자용 — 전체 상태 포함) ────────────────────────────────────
@admin_bp.route('/notices', methods=['GET'])
@admin_required
def admin_get_notices():
    """관리자 공고 목록.

    Query params:
      adminStatus — review | approved | rejected | hold (복수: 쉼표구분, 기본: review)
      source      — 발주처 필터 (복수: 쉼표구분)
      search      — 제목/국가 검색
      page        — 페이지 (기본 1)
      perPage     — 건수 (기본 50, 최대 200)
      sort        — created(기본) | relevance | deadline
    """
    admin_status_param = request.args.get('adminStatus', 'review')
    source_param = request.args.get('source', '')
    search_param = request.args.get('search', '')
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('perPage', 50, type=int)), 200)
    sort_param = request.args.get('sort', 'created')

    query = BidNotice.query
    statuses = [s.strip() for s in admin_status_param.split(',') if s.strip()]
    if statuses:
        query = query.filter(BidNotice.admin_status.in_(statuses))

    if source_param:
        sources = [s.strip() for s in source_param.split(',') if s.strip()]
        if sources:
            query = query.filter(BidNotice.source.in_(sources))

    if search_param:
        like = f'%{search_param}%'
        query = query.filter(
            BidNotice.title.ilike(like) |
            BidNotice.country.ilike(like) |
            BidNotice.project_name.ilike(like)
        )

    if sort_param == 'relevance':
        query = query.order_by(BidNotice.relevance_score.desc(), BidNotice.created_at.desc())
    elif sort_param == 'deadline':
        query = query.order_by(
            BidNotice.deadline_date.asc().nullslast(), BidNotice.created_at.desc()
        )
    else:
        query = query.order_by(BidNotice.created_at.desc())

    total = query.count()
    notices = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'success': True,
        'data': [n.to_admin_dict() for n in notices],
        'pagination': {
            'page': page,
            'perPage': per_page,
            'total': total,
            'totalPages': (total + per_page - 1) // per_page if total else 0,
        },
    })


@admin_bp.route('/notices/<int:notice_id>', methods=['GET'])
@admin_required
def admin_get_notice(notice_id):
    notice = BidNotice.query.get_or_404(notice_id)
    return jsonify({'success': True, 'data': notice.to_admin_dict()})


@admin_bp.route('/notices/<int:notice_id>', methods=['PATCH'])
@admin_required
def admin_patch_notice(notice_id):
    """공고 필드 수정.

    Patchable fields:
      adminStatus — review | approved | rejected | hold
      adminNote   — 검수 메모
      assignedTo  — 담당자
      titleKo     — 한글 제목
      krcTags     — KRC 태그 배열
      relevanceScore — 관련성 점수 (0-100)
      lat, lng    — 좌표 보정
    """
    notice = BidNotice.query.get_or_404(notice_id)
    body = request.get_json(silent=True) or {}

    allowed = {
        'adminStatus': ('admin_status', str),
        'adminNote': ('admin_note', str),
        'assignedTo': ('assigned_to', str),
        'titleKo': ('title_ko', str),
        'krcTags': ('krc_tags', list),
        'relevanceScore': ('relevance_score', int),
        'lat': ('lat', float),
        'lng': ('lng', float),
    }
    valid_admin_statuses = {'review', 'approved', 'rejected', 'hold'}

    for json_key, (model_attr, expected_type) in allowed.items():
        if json_key not in body:
            continue
        val = body[json_key]
        if json_key == 'adminStatus' and val not in valid_admin_statuses:
            return jsonify({'success': False,
                            'error': f'adminStatus must be one of {valid_admin_statuses}'}), 400
        if expected_type == int:
            try:
                val = int(val)
            except (TypeError, ValueError):
                continue
        elif expected_type == float:
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
        setattr(notice, model_attr, val)

    notice.updated_at = datetime.utcnow()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

    return jsonify({'success': True, 'data': notice.to_admin_dict()})


@admin_bp.route('/notices/<int:notice_id>', methods=['DELETE'])
@admin_required
def admin_delete_notice(notice_id):
    notice = BidNotice.query.get_or_404(notice_id)
    try:
        db.session.delete(notice)
        db.session.commit()
        return jsonify({'success': True, 'id': notice_id})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 일괄 액션 ─────────────────────────────────────────────────────────────────
@admin_bp.route('/notices/bulk', methods=['POST'])
@admin_required
def admin_bulk_action():
    """일괄 상태 변경.

    Body: {"ids": [1,2,3], "action": "approve" | "reject" | "hold" | "delete"}
    """
    body = request.get_json(silent=True) or {}
    ids = body.get('ids', [])
    action = body.get('action', '')

    if not ids or not isinstance(ids, list):
        return jsonify({'success': False, 'error': 'ids 필드 필요'}), 400

    action_map = {
        'approve': 'approved',
        'reject': 'rejected',
        'hold': 'hold',
        'review': 'review',
    }

    if action == 'delete':
        try:
            deleted = (BidNotice.query.filter(BidNotice.id.in_(ids))
                       .delete(synchronize_session=False))
            db.session.commit()
            return jsonify({'success': True, 'deleted': deleted})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)}), 500

    new_status = action_map.get(action)
    if not new_status:
        return jsonify({'success': False, 'error': f'알 수 없는 action: {action}'}), 400

    try:
        updated = (BidNotice.query.filter(BidNotice.id.in_(ids))
                   .update({'admin_status': new_status, 'updated_at': datetime.utcnow()},
                           synchronize_session=False))
        db.session.commit()
        return jsonify({'success': True, 'updated': updated, 'status': new_status})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 통계 (관리자용 — 검수 대기 포함) ─────────────────────────────────────────
@admin_bp.route('/stats', methods=['GET'])
@admin_required
def admin_stats():
    """관리자 통계 — 상태별 건수 포함."""
    by_status = db.session.query(
        BidNotice.admin_status, func.count(BidNotice.id)
    ).group_by(BidNotice.admin_status).all()

    by_source = db.session.query(
        BidNotice.source, func.count(BidNotice.id)
    ).group_by(BidNotice.source).all()

    total = BidNotice.query.count()
    last_run = ScrapingRun.query.order_by(ScrapingRun.run_at.desc()).first()

    return jsonify({
        'success': True,
        'total': total,
        'by_status': {s: c for s, c in by_status},
        'by_source': {s: c for s, c in by_source},
        'last_run': last_run.to_dict() if last_run else None,
    })


# ── CSV 내보내기 ───────────────────────────────────────────────────────────────
@admin_bp.route('/notices/export', methods=['GET'])
@admin_required
def admin_export_csv():
    """승인된 공고 CSV 다운로드."""
    admin_status = request.args.get('adminStatus', 'approved')
    notices = BidNotice.query.filter_by(admin_status=admin_status).all()

    output = io.StringIO()
    writer = csv.writer(output)

    headers = [
        'ID', '발주처', '제목', '국가', '분야', '공고유형',
        '게시일', '마감일', 'D-day', '금액', '통화',
        'KRC태그', '관련성점수', '원문URL', '수집일',
    ]
    writer.writerow(headers)

    for n in notices:
        days_left = n._days_left()
        writer.writerow([
            n.id,
            n.source,
            n.title,
            n.country or '',
            n.sector or '',
            n.notice_type or '',
            str(n.posted_date) if n.posted_date else '',
            str(n.deadline_date) if n.deadline_date else '',
            days_left if days_left is not None else '',
            str(n.amount_value) if n.amount_value else (n.contract_value or ''),
            n.amount_currency or '',
            ','.join(n.krc_tags) if isinstance(n.krc_tags, list) else '',
            n.relevance_score or 0,
            n.source_url,
            str(n.created_at.date()) if n.created_at else '',
        ])

    output.seek(0)
    filename = f'krc_worldmarket_{datetime.utcnow().strftime("%Y%m%d")}.csv'
    return Response(
        output.getvalue(),
        mimetype='text/csv; charset=utf-8-sig',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )
