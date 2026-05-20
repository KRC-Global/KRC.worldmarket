#!/usr/bin/env python3
"""
SQLite → Supabase PostgreSQL 데이터 마이그레이션 스크립트

사용법:
  SQLITE_URL=sqlite:///backend/krc_worldmarket.db \
  DATABASE_URL=postgresql://postgres.[ref]:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:5432/postgres \
  python scripts/migrate_to_supabase.py
"""
import os
import sys

# 백엔드 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

SQLITE_URL = os.environ.get('SQLITE_URL', 'sqlite:///backend/krc_worldmarket.db')
POSTGRES_URL = os.environ.get('DATABASE_URL', '')

if not POSTGRES_URL or POSTGRES_URL.startswith('sqlite'):
    print('ERROR: DATABASE_URL에 Supabase PostgreSQL URL을 설정하세요.')
    sys.exit(1)

print(f'소스 (SQLite): {SQLITE_URL}')
print(f'대상 (PostgreSQL): {POSTGRES_URL[:60]}...')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# SQLite 연결
sqlite_engine = create_engine(SQLITE_URL)
SQLiteSession = sessionmaker(bind=sqlite_engine)

# PostgreSQL 연결
pg_engine = create_engine(POSTGRES_URL)
PGSession = sessionmaker(bind=pg_engine)

# 모델 import (SQLAlchemy ORM)
os.environ['DATABASE_URL'] = SQLITE_URL  # 모델 로드 시 SQLite 사용
from models import db, BidNotice, ScrapingRun
from flask import Flask
from config import config

def make_app(db_url):
    app = Flask(__name__)
    app.config.from_object(config['default'])
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    db.init_app(app)
    return app

# ── 1. PostgreSQL에 테이블 생성 ──────────────────────────────────────────────
print('\n[1] PostgreSQL에 테이블 생성 중...')
pg_app = make_app(POSTGRES_URL)
with pg_app.app_context():
    db.create_all()
    print('  bid_notices, scraping_runs 테이블 생성 완료.')

# ── 2. SQLite에서 데이터 읽기 ─────────────────────────────────────────────────
print('\n[2] SQLite에서 데이터 읽는 중...')
sqlite_app = make_app(SQLITE_URL)
with sqlite_app.app_context():
    notices = BidNotice.query.all()
    runs    = ScrapingRun.query.all()

    notice_dicts = []
    for n in notices:
        d = {c.name: getattr(n, c.name)
             for c in n.__table__.columns}
        notice_dicts.append(d)

    run_dicts = []
    for r in runs:
        d = {c.name: getattr(r, c.name)
             for c in r.__table__.columns}
        run_dicts.append(d)

print(f'  bid_notices: {len(notice_dicts)}건')
print(f'  scraping_runs: {len(run_dicts)}건')

# ── 3. PostgreSQL에 데이터 삽입 ──────────────────────────────────────────────
print('\n[3] PostgreSQL에 데이터 삽입 중...')
with pg_app.app_context():
    # 기존 데이터 확인
    existing = BidNotice.query.count()
    if existing > 0:
        ans = input(f'  PostgreSQL에 이미 {existing}건의 데이터가 있습니다. 계속할까요? [y/N] ')
        if ans.lower() != 'y':
            print('취소.')
            sys.exit(0)

    inserted_notices = 0
    for d in notice_dicts:
        # id 제외하고 삽입 (PostgreSQL이 자동 생성)
        d_copy = {k: v for k, v in d.items() if k != 'id'}
        notice = BidNotice(**d_copy)
        db.session.add(notice)
        inserted_notices += 1

    inserted_runs = 0
    for d in run_dicts:
        d_copy = {k: v for k, v in d.items() if k != 'id'}
        run = ScrapingRun(**d_copy)
        db.session.add(run)
        inserted_runs += 1

    db.session.commit()
    print(f'  bid_notices: {inserted_notices}건 삽입 완료')
    print(f'  scraping_runs: {inserted_runs}건 삽입 완료')

print('\n✅ 마이그레이션 완료!')
print('이제 backend/.env의 DATABASE_URL을 Supabase PostgreSQL URL로 변경하세요.')
