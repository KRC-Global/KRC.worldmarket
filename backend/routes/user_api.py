"""
KRC World Market — 일반 유저 API
북마크된 공고 notice_id 목록을 받아 공고 상세 데이터를 반환.
Supabase JWT 인증 필요 (admin 아닌 일반 유저도 허용).
"""
from flask import Blueprint, request, jsonify
from models import BidNotice
from auth import auth_required

user_bp = Blueprint('user', __name__)


@user_bp.route('/bookmarks', methods=['GET'])
@auth_required
def get_bookmarked_notices():
    """북마크된 공고 목록 반환.
    Query param: ids=1,2,3  (notice_id 콤마 구분)
    """
    ids_param = request.args.get('ids', '')
    ids = [int(i) for i in ids_param.split(',') if i.strip().isdigit()]
    if not ids:
        return jsonify({'success': True, 'data': []})

    notices = (BidNotice.query
               .filter(BidNotice.id.in_(ids),
                       BidNotice.admin_status == 'approved')
               .all())
    return jsonify({
        'success': True,
        'data': [n.to_public_dict() for n in notices],
    })
