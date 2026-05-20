#!/usr/bin/env python3
"""
KRC World Market — 프로덕션 DB 초기화 (1회 실행용)

Vercel/Supabase Postgres 환경에서 첫 배포 전 한 번만 실행:
  DATABASE_URL=postgresql://... python scripts/init_db.py

로컬 개발은 Flask가 자동 처리하므로 이 스크립트 불필요.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'), override=False)

if not os.environ.get('DATABASE_URL'):
    print('[ERROR] DATABASE_URL 환경변수가 설정되지 않았습니다.')
    print('  export DATABASE_URL=postgresql://...')
    sys.exit(1)

os.environ['FLASK_ENV'] = 'production'

from app import app, _run_migrations
from models import db

with app.app_context():
    print('[init_db] 테이블 생성 중...')
    db.create_all()
    print('[init_db] 마이그레이션 실행 중...')
    _run_migrations()
    print('[init_db] 완료.')
