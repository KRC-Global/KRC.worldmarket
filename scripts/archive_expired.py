#!/usr/bin/env python3
"""
마감/오래된 공고 정리 스크립트
사용법: python scripts/archive_expired.py [--days N]
"""
import os
import sys
import json
import requests

API_URL = os.environ.get('API_URL', 'http://localhost:5001')
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'change-this-in-production')

days = 60
for i, arg in enumerate(sys.argv[1:]):
    if arg == '--days' and i + 1 < len(sys.argv[1:]):
        try:
            days = int(sys.argv[i + 2])
        except (IndexError, ValueError):
            pass

print(f'기준: {days}일 이상 경과 또는 마감된 공고 삭제...')

try:
    resp = requests.post(
        f'{API_URL}/api/admin/cleanup',
        headers={'X-Admin-Key': ADMIN_KEY},
        params={'days': days},
        timeout=60,
    )
    result = resp.json()
    print(json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    print(f'오류: {e}')
    sys.exit(1)
