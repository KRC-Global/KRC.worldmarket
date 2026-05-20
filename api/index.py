"""
Vercel serverless 진입점.
backend/app.py 의 Flask app을 Vercel Python 런타임에 노출한다.
"""
import sys
import os
import traceback

# backend 디렉토리를 sys.path 에 추가
_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
sys.path.insert(0, _backend)

_init_error = None

try:
    from app import app  # noqa: E402  (Vercel이 'app' WSGI callable을 찾음)
except Exception:
    _init_error = traceback.format_exc()
    from flask import Flask, jsonify
    app = Flask(__name__)

    @app.route('/api/debug')
    def _debug():
        return jsonify({'init_error': _init_error, 'sys_path': sys.path[:5]}), 500
