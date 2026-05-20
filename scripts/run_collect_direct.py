#!/usr/bin/env python3
"""
KRC World Market — 직접 수집 스크립트 (HTTP 없이 Flask app context 안에서 실행)
launchd / cron 에서 매일 자동 호출되는 진입점.

사용법:
  python scripts/run_collect_direct.py            # 전체 소스
  python scripts/run_collect_direct.py worldbank adb
환경변수:
  TRANSLATE_AFTER_COLLECT=0   번역 단계 스킵
  TRANSLATE_LIMIT=50          1회 번역 최대 건수
"""
import os
import sys
import json
from pathlib import Path

# 프로젝트 루트 / backend 디렉토리를 sys.path 에 추가
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / 'backend'
sys.path.insert(0, str(BACKEND))

# Flask app 초기화
os.environ.setdefault('FLASK_ENV', 'default')
from app import app  # noqa: E402
from routes.collector import _do_collect  # noqa: E402

sources = sys.argv[1:] if len(sys.argv) > 1 else None

with app.app_context():
    # 테이블/마이그레이션 보장
    from models import db
    from app import _run_migrations
    db.create_all()
    _run_migrations()

    if sources:
        print(f'수집 대상: {sources}', flush=True)
    else:
        print('전체 소스 수집 시작...', flush=True)

    result = _do_collect(sources=sources, trigger='scheduled')

print(json.dumps(result, ensure_ascii=False, indent=2))
sys.exit(0 if result.get('success') else 1)
