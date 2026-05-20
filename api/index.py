"""
Vercel serverless 진입점.
backend/app.py 의 Flask app을 Vercel Python 런타임에 노출한다.
"""
import sys
import os
import traceback

# backend 디렉토리를 sys.path 에 추가 (절대경로)
_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
sys.path.insert(0, _backend)

from app import app  # Vercel이 top-level 'app' WSGI callable을 찾음

# 임시 디버그: 런타임 에러 내용을 JSON으로 반환 (에러 파악 후 제거 예정)
from flask import jsonify

@app.errorhandler(Exception)
def _handle_exception(e):
    tb = traceback.format_exc()
    app.logger.error(tb)
    return jsonify({'error': str(e), 'trace': tb}), 500
