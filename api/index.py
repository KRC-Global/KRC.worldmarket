"""
Vercel serverless 진입점.
backend/app.py 의 Flask app을 Vercel Python 런타임에 노출한다.
"""
import sys
import os

# backend 디렉토리를 sys.path 에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app import app  # noqa: E402  (Vercel이 'app' WSGI callable을 찾음)
