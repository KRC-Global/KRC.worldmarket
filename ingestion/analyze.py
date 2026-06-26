"""분석: 첨부 PDF 텍스트 추출 + LLM 한국어 개요 생성.

요약 LLM 우선순위:
  1) GROQ_API_KEY 있으면 Groq(OpenAI 호환 API) — GitHub Actions 등 클라우드 자동화용
  2) 로컬 Hermes(openai-codex 프로필) — 개발 머신용
  3) 원문 필드 기반 최소 개요 폴백
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Optional

HERMES_BIN = os.environ.get("HERMES_BIN", "/Users/yun/.local/bin/hermes")
HERMES_PROFILE = os.environ.get("HERMES_PROFILE", "mdb-tender")

# Groq (OpenAI 호환). 모델은 GROQ_MODEL 로 교체 가능.
GROQ_BASE_URL = os.environ.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

SUMMARY_KEYS = ["사업명", "발주처", "국가", "분야", "규모", "마감일", "자격요건", "핵심요약"]


def extract_pdf_text(data: bytes, max_chars: int = 20000) -> str:
    """PDF 바이트에서 본문 텍스트 추출 (pymupdf)."""
    import fitz  # pymupdf

    text_parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
            if sum(len(t) for t in text_parts) > max_chars:
                break
    return "".join(text_parts)[:max_chars]


def _prompt(notice: dict) -> str:
    body = (notice.get("raw_text") or "")[:8000]
    return (
        "다음 MDB 발주공고를 분석해 한국어 개요를 JSON 으로만 출력해라. "
        f"키는 정확히 {SUMMARY_KEYS} 를 사용하고 값은 간결한 한국어 문자열. "
        "모르면 빈 문자열.\n\n"
        f"[제목] {notice.get('title','')}\n"
        f"[기관] {notice.get('source','')}\n"
        f"[국가] {notice.get('country','')}\n"
        f"[본문] {body}\n"
    )


def _extract_json(text: str) -> Optional[dict]:
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _summarize_groq(prompt: str) -> Optional[dict]:
    """Groq(OpenAI 호환)로 JSON 요약. 키 없거나 실패 시 None."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
        res = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": "너는 개발협력 발주공고 분석가다. 반드시 JSON 객체로만 답한다."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=60,
        )
        return _extract_json(res.choices[0].message.content or "")
    except Exception as e:  # noqa: BLE001
        print(f"  [analyze-groq] 실패: {e}")
        return None


def _summarize_hermes(prompt: str) -> Optional[dict]:
    """로컬 Hermes CLI 요약. 바이너리 없거나 실패 시 None."""
    if not os.path.exists(HERMES_BIN):
        return None
    try:
        cmd = f"{shlex.quote(HERMES_BIN)} chat -Q --profile {shlex.quote(HERMES_PROFILE)} -q {shlex.quote(prompt)}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=180)
        return _extract_json(res.stdout.strip())
    except Exception:
        return None


def summarize(notice: dict) -> Optional[dict]:
    """공고 1건을 한국어 구조화 개요(dict)로 요약. 실패 시 폴백 dict."""
    prompt = _prompt(notice)
    result = _summarize_groq(prompt) or _summarize_hermes(prompt)
    if result:
        return result
    # 폴백: LLM 없이 기본 개요
    return {
        "사업명": notice.get("title", ""),
        "발주처": notice.get("source", "").upper(),
        "국가": notice.get("country", "") or "",
        "분야": notice.get("ag_subsector", "") or "농업",
        "규모": "",
        "마감일": notice.get("deadline_at", "") or "",
        "자격요건": "",
        "핵심요약": (notice.get("raw_text", "") or "")[:200],
    }
