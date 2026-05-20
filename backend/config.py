"""
KRC World Market — Flask Configuration
"""
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'krc-worldmarket-dev-secret')

    # SQLite (기본, 로컬 개발)
    # PostgreSQL 사용 시 DATABASE_URL 환경변수로 주입
    _db_url = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.join(BASE_DIR, "krc_worldmarket.db")}'
    # Supabase pooler는 postgres:// 스킴을 쓰는 경우 SQLAlchemy가 postgresql://로 인식해야 함
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 서버리스(Vercel) 환경: 연결 풀 크기 최소화, SSL 필수
    _is_postgres = 'postgresql' in _db_url or 'postgres' in _db_url
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        **({'pool_size': 1, 'max_overflow': 0,
            'connect_args': {'sslmode': 'require'}}
           if _is_postgres else {}),
    }

    # 관리자 KEY (X-Admin-Key 헤더 — 수집 스크립트 후방 호환)
    ADMIN_KEY = os.environ.get('ADMIN_KEY', 'change-this-in-production')

    # Supabase
    SUPABASE_URL        = os.environ.get('SUPABASE_URL', '')
    SUPABASE_ANON_KEY   = os.environ.get('SUPABASE_ANON_KEY', '')
    SUPABASE_JWT_SECRET = os.environ.get('SUPABASE_JWT_SECRET', '')

    # 수집기 API 키
    UNGM_API_KEY   = os.environ.get('UNGM_API_KEY', '')
    KOICA_API_KEY  = os.environ.get('KOICA_API_KEY', '')

    # Rate limiting
    RATELIMIT_DEFAULT = '100/minute'
    RATELIMIT_STORAGE_URI = 'memory://'

    # CORS
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', 'https://krc-worldmarket.vercel.app')


config = {
    'development': DevelopmentConfig,
    'production':  ProductionConfig,
    'default':     DevelopmentConfig,
}
