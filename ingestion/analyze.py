"""분석: 첨부 PDF 텍스트 추출 + Codex(LLM) 한국어 개요 생성.

요약 LLM 은 Hermes 의 openai-codex 프로필을 통해 호출한다(별도 API 키 불필요).
Hermes 가 없거나 실패하면 원문 필드 기반의 최소 개요로 폴백한다.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Optional

HERMES_BIN = os.environ.get("HERMES_BIN", "/Users/yun/.local/bin/hermes")
HERMES_PROFILE = os.environ.get("HERMES_PROFILE", "mdb-tender")

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


def summarize(notice: dict) -> Optional[dict]:
    """공고 1건을 한국어 구조화 개요(dict)로 요약. 실패 시 폴백 dict."""
    prompt = _prompt(notice)
    try:
        cmd = f"{shlex.quote(HERMES_BIN)} chat -Q --profile {shlex.quote(HERMES_PROFILE)} -q {shlex.quote(prompt)}"
        res = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=180
        )
        out = res.stdout.strip()
        start, end = out.find("{"), out.rfind("}")
        if start != -1 and end != -1:
            return json.loads(out[start : end + 1])
    except Exception:
        pass
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
