"""히어로 이미지 생성 → Supabase Storage 업로드 → public URL 반환.

기본 제공자는 Pollinations(무료·무키, FLUX). IMAGE_PROVIDER=openai 로 바꾸고
OPENAI_API_KEY 를 주면 gpt-image-1 사용(유료). 실패/무키 시 None(스킵).
"""
from __future__ import annotations

import base64
import hashlib
import os
import urllib.parse
from typing import Optional

from . import supabase_client

IMAGE_PROVIDER = os.environ.get("IMAGE_PROVIDER", "pollinations")
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
POLLINATIONS_MODEL = os.environ.get("POLLINATIONS_MODEL", "flux")
_W, _H = 1280, 720


def _prompt(notice: dict) -> str:
    summary = notice.get("summary") or {}
    topic = summary.get("사업명") or notice.get("title", "")
    country = summary.get("국가") or notice.get("country", "")
    return (
        "Clean modern flat infographic illustration for an agriculture development "
        f"project. Theme: {topic}. Country/region: {country}. "
        "Editorial vector style, muted earth tones, no text, no logos, 16:9."
    )


def _upload(notice: dict, img: bytes) -> Optional[str]:
    if not img or len(img) < 1500:  # 에러/플레이스홀더 이미지 방지
        return None
    path = f"{notice['source']}/{notice['source_notice_id']}.png".replace(" ", "_")
    return supabase_client.upload_bytes(
        supabase_client.BUCKET_IMAGES, path, img, "image/png"
    )


def _gen_pollinations(notice: dict) -> Optional[bytes]:
    """Pollinations.ai — 무료·무키. URL 호출로 이미지 바이트 반환."""
    import requests as req

    prompt = urllib.parse.quote(_prompt(notice))
    seed = int(hashlib.md5(str(notice.get("source_notice_id", "")).encode()).hexdigest()[:8], 16)
    url = (f"https://image.pollinations.ai/prompt/{prompt}"
           f"?width={_W}&height={_H}&nologo=true&model={POLLINATIONS_MODEL}&seed={seed}")
    try:
        r = req.get(url, timeout=120, headers={"User-Agent": "balju-gonggo-bot/0.1"})
        if r.status_code == 200 and r.content and "image" in r.headers.get("content-type", ""):
            return r.content
        print(f"  [illustrate-pollinations] HTTP {r.status_code} ct={r.headers.get('content-type')}")
    except Exception as e:  # noqa: BLE001
        print(f"  [illustrate-pollinations] 실패: {e}")
    return None


def _gen_openai(notice: dict) -> Optional[bytes]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        result = client.images.generate(
            model=OPENAI_IMAGE_MODEL, prompt=_prompt(notice), size="1536x1024", n=1
        )
        return base64.b64decode(result.data[0].b64_json)
    except Exception as e:  # noqa: BLE001
        print(f"  [illustrate-openai] 실패: {e}")
        return None


def generate(notice: dict) -> Optional[str]:
    """공고용 히어로 이미지를 생성·업로드하고 public URL 반환. 실패 시 None."""
    if IMAGE_PROVIDER == "openai":
        img = _gen_openai(notice) or _gen_pollinations(notice)
    else:
        img = _gen_pollinations(notice)
    return _upload(notice, img) if img else None
