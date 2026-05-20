"""
KRC World Market — Flask Application
외부 발주공고 공개 탐색 플랫폼
"""
import os
from flask import Flask, send_from_directory
from flask_cors import CORS

try:
    from dotenv import load_dotenv
    _here = os.path.dirname(os.path.abspath(__file__))
    for _env in (os.path.join(_here, '.env'), os.path.join(_here, '..', '.env')):
        if os.path.isfile(_env):
            load_dotenv(_env, override=False)
            break
except Exception:
    pass

from config import config

app = Flask(__name__, static_folder='..', static_url_path='')

config_name = os.environ.get('FLASK_ENV', 'default')
app.config.from_object(config[config_name])

# CORS — 공개 API는 전체 허용, 관리자 API는 admin_api.py에서 별도 제한
CORS(app,
     resources={r"/api/*": {"origins": app.config.get('CORS_ORIGINS', '*')}},
     allow_headers=["Content-Type", "X-Admin-Key", "Authorization"],
     methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"])

# DB 초기화
from models import db
db.init_app(app)

_tables_created = False
_IS_PRODUCTION = os.environ.get('FLASK_ENV') == 'production'


@app.before_request
def ensure_tables():
    """개발 환경에서만 자동 테이블 생성.
    프로덕션(Vercel)에서는 scripts/init_db.py 를 한 번 실행해 DB를 초기화한다.
    """
    if _IS_PRODUCTION:
        return
    global _tables_created
    if not _tables_created:
        db.create_all()
        _run_migrations()
        _tables_created = True


def _run_migrations():
    """idempotent 마이그레이션 — 컬럼 추가 등"""
    migrations = [
        "ALTER TABLE bid_notices ADD COLUMN source_id VARCHAR(200)",
        "ALTER TABLE bid_notices ADD COLUMN source_hash VARCHAR(64)",
        "ALTER TABLE bid_notices ADD COLUMN last_seen_at DATETIME",
        "ALTER TABLE bid_notices ADD COLUMN region VARCHAR(100)",
        "ALTER TABLE bid_notices ADD COLUMN notice_type VARCHAR(150)",
        "ALTER TABLE bid_notices ADD COLUMN procurement_method VARCHAR(200)",
        "ALTER TABLE bid_notices ADD COLUMN procurement_category VARCHAR(100)",
        "ALTER TABLE bid_notices ADD COLUMN project_id VARCHAR(100)",
        "ALTER TABLE bid_notices ADD COLUMN project_name TEXT",
        "ALTER TABLE bid_notices ADD COLUMN posted_date DATE",
        "ALTER TABLE bid_notices ADD COLUMN deadline_date DATE",
        "ALTER TABLE bid_notices ADD COLUMN amount_value NUMERIC(18,2)",
        "ALTER TABLE bid_notices ADD COLUMN amount_currency VARCHAR(10)",
        "ALTER TABLE bid_notices ADD COLUMN krc_tags JSON",
        "ALTER TABLE bid_notices ADD COLUMN relevance_score INTEGER DEFAULT 0",
        "ALTER TABLE bid_notices ADD COLUMN relevance_reason TEXT",
        "ALTER TABLE bid_notices ADD COLUMN lat FLOAT",
        "ALTER TABLE bid_notices ADD COLUMN lng FLOAT",
        "ALTER TABLE bid_notices ADD COLUMN admin_status VARCHAR(20) DEFAULT 'review'",
        "ALTER TABLE bid_notices ADD COLUMN admin_note TEXT",
        "ALTER TABLE bid_notices ADD COLUMN assigned_to VARCHAR(100)",
        "ALTER TABLE bid_notices ADD COLUMN updated_at DATETIME",
        "ALTER TABLE bid_notices ADD COLUMN project_name_ko TEXT",
        "ALTER TABLE bid_notices ADD COLUMN notice_text TEXT",
        "ALTER TABLE bid_notices ADD COLUMN notice_text_ko TEXT",
        "ALTER TABLE bid_notices ADD COLUMN translated_at DATETIME",
        "ALTER TABLE scraping_runs ADD COLUMN total_updated INTEGER DEFAULT 0",
        "ALTER TABLE scraping_runs ADD COLUMN error TEXT",
    ]
    with db.engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(db.text(sql))
                conn.commit()
            except Exception:
                conn.rollback()


# 블루프린트 등록
from routes.public_api import public_bp
from routes.admin_api  import admin_bp
from routes.collector  import collector_bp
from routes.user_api   import user_bp

app.register_blueprint(public_bp,    url_prefix='/api')
app.register_blueprint(admin_bp,     url_prefix='/api/admin')
app.register_blueprint(collector_bp, url_prefix='/api/admin')
app.register_blueprint(user_bp,      url_prefix='/api/user')


# 정적 파일 서빙 (index.html, admin.html)
@app.route('/')
def index():
    return send_from_directory('..', 'index.html')

@app.route('/admin.html')
def admin():
    return send_from_directory('..', 'admin.html')

@app.route('/analytics.html')
def analytics():
    return send_from_directory('..', 'analytics.html')


@app.errorhandler(404)
def not_found(e):
    from flask import jsonify, request
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'error': 'Not found'}), 404
    return send_from_directory('..', 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)
