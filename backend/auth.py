"""
KRC World Market — 공유 인증 데코레이터

우선순위:
  1. Supabase JWT (Authorization: Bearer <token>) — 브라우저 관리자
  2. X-Admin-Key 헤더 / ?key= 파라미터 — 수집 스크립트 후방 호환
"""
import os
import jwt
from functools import wraps
from flask import request, jsonify, current_app


def _verify_supabase_jwt(token: str) -> dict | None:
    """Supabase JWT를 검증하고 payload를 반환. 실패 시 None."""
    secret = os.environ.get('SUPABASE_JWT_SECRET', '')
    if not secret:
        return None
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=['HS256'],
            options={'verify_exp': True},
        )
        return payload
    except jwt.PyJWTError:
        return None


def admin_required(f):
    """관리자 전용 엔드포인트 데코레이터.
    JWT app_metadata.role == 'admin' 또는 X-Admin-Key 일치 시 통과.
    GET 전용 다운로드용 ?token= query param도 지원.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Path 1: Supabase JWT (Authorization 헤더 또는 ?token= query param)
        auth_header = request.headers.get('Authorization', '')
        token_from_header = auth_header[7:] if auth_header.startswith('Bearer ') else None
        token_from_param  = request.args.get('token', '')
        jwt_token = token_from_header or token_from_param
        if jwt_token:
            payload = _verify_supabase_jwt(jwt_token)
            if payload:
                app_meta = payload.get('app_metadata') or {}
                if app_meta.get('role') == 'admin':
                    return f(*args, **kwargs)

        # Path 2: X-Admin-Key (수집 스크립트 후방 호환)
        key = (request.headers.get('X-Admin-Key')
               or request.args.get('key', ''))
        admin_key = current_app.config.get('ADMIN_KEY', '')
        if admin_key and key == admin_key:
            return f(*args, **kwargs)

        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    return decorated


def auth_required(f):
    """일반 인증 데코레이터 (admin 아닌 일반 유저도 허용).
    유효한 Supabase JWT가 있으면 통과하고 request.user_id를 설정.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        token = auth_header[7:]
        payload = _verify_supabase_jwt(token)
        if not payload:
            return jsonify({'success': False, 'error': 'Invalid or expired token'}), 401
        request.user_id = payload.get('sub')
        return f(*args, **kwargs)
    return decorated
