"""인포그래픽/히어로 이미지 생성 — OpenAI gpt-image.

OPENAI_API_KEY (Codex OAuth 와 별개) 필요. 생성 후 Supabase Storage 에 업로드하고
public URL 을 반환. 키가 없으면 None 반환(스킵).
"""
from __future__ import annotations

import base64
import os
from typing import Optional

from . import supabase_client

MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")


def _prompt(notice: dict) -> str:
    summary = notice.get("summary") or {}
    topic = summary.get("사업명") or notice.get("title", "")
    country = summary.get("국가") or notice.get("country", "")
    return (
        "Clean modern flat infographic illustration for an agriculture development "
        f"project. Theme: {topic}. Country/region: {country}. "
        "Editorial vector style, muted earth tones, no text, no logos, 16:9."
    )


def generate(notice: dict) -> Optional[str]:
    """공고용 히어로 이미지를 생성·업로드하고 public URL 반환. 실패/무키 시 None."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        result = client.images.generate(
            model=MODEL, prompt=_prompt(notice), size="1536x1024", n=1
        )
        b64 = result.data[0].b64_json
        img_bytes = base64.b64decode(b64)
        path = f"{notice['source']}/{notice['source_notice_id']}.png".replace(" ", "_")
        return supabase_client.upload_bytes(
            supabase_client.BUCKET_IMAGES, path, img_bytes, "image/png"
        )
    except Exception as e:  # noqa: BLE001
        print(f"  [illustrate] 실패: {e}")
        return None
