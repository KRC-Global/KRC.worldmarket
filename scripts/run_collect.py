#!/usr/bin/env python3
"""
수동 수집 트리거 스크립트
사용법: python scripts/run_collect.py [source1 source2 ...]
예시:
  python scripts/run_collect.py                    # 전체 수집
  python scripts/run_collect.py worldbank adb      # 지정 소스만
"""
import os
import sys
import json
import requests

API_URL = os.environ.get('API_URL', 'http://localhost:5001')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'change-this-in-production')

sources = sys.argv[1:] if len(sys.argv) > 1 else None

payload = {'trigger': 'manual'}
if sources:
    payload['sources'] = sources
    print(f'수집 대상: {sources}')
else:
    print('전체 소스 수집 시작...')

try:
    resp = requests.post(
        f'{API_URL}/api/admin/collect',
        headers={'X-Admin-Key': ADMIN_KEY, 'Content-Type': 'application/json'},
        json=payload,
        timeout=180,
    )
    result = resp.json()
    print(json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    print(f'오류: {e}')
    sys.exit(1)
