"""
KRC World Market — 영문 → 한국어 번역 모듈
Codex CLI (ChatGPT 구독) 를 백엔드로 사용.
"""
import os
import re
import subprocess
import tempfile
import time
import logging
from pathlib import Path

log = logging.getLogger(__name__)

CODEX_BIN = os.environ.get('CODEX_BIN', 'codex')
BATCH_SIZE = int(os.environ.get('TRANSLATE_BATCH_SIZE', '10'))
CALL_TIMEOUT = int(os.environ.get('TRANSLATE_CALL_TIMEOUT', '180'))
SLEEP_BETWEEN = float(os.environ.get('TRANSLATE_SLEEP', '1.0'))


def _call_codex(prompt: str) -> str | None:
    """codex exec 한 번 호출. 마지막 메시지를 문자열로 반환. 실패 시 None."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        out_path = f.name
    try:
        proc = subprocess.run(
            [
                CODEX_BIN, 'exec',
                '--skip-git-repo-check',
                '--ephemeral',
                '--color', 'never',
                '-c', 'model_reasoning_effort=low',
                '-o', out_path,
                prompt,
            ],
            capture_output=True,
            text=True,
            timeout=CALL_TIMEOUT,
        )
        if proc.returncode != 0:
            log.warning('codex exit=%s stderr=%s', proc.returncode, proc.stderr[:300])
            return None
        return Path(out_path).read_text(encoding='utf-8').strip()
    except subprocess.TimeoutExpired:
        log.warning('codex timeout after %ss', CALL_TIMEOUT)
        return None
    except Exception as e:
        log.warning('codex call failed: %s', e)
        return None
    finally:
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass


def translate_batch(texts: list[str]) -> list[str | None]:
    """영문 텍스트 리스트 → 한글 번역 리스트.

    각 위치의 반환값:
      - '' (빈 문자열): 입력이 빈 문자열이거나 whitespace 뿐인 경우
      - str: 번역 성공
      - None: 번역 실패 (codex 호출 자체가 실패했거나 응답 파싱 실패)

    호출 측은 None 을 보고 "다음 차례에 재시도" 같은 정책을 결정할 수 있다.
    """
    if not texts:
        return []

    # 빈 입력은 ''로, 비어있지 않은 입력은 일단 None (실패) 으로 시작
    out: list[str | None] = []
    items: list[tuple[int, str]] = []
    for i, t in enumerate(texts):
        if (t or '').strip():
            out.append(None)
            items.append((i, t))
        else:
            out.append('')

    if not items:
        return out

    for chunk_start in range(0, len(items), BATCH_SIZE):
        chunk = items[chunk_start:chunk_start + BATCH_SIZE]
        numbered = '\n'.join(f'[{n+1}] {t}' for n, (_, t) in enumerate(chunk))
        prompt = (
            '아래 영문들을 자연스럽고 정확한 한국어로 번역해줘.\n'
            '출력 규칙 (엄격히 준수):\n'
            '- 각 번역 앞에 [번호] 유지. 예: [1] 번역내용\n'
            '- 번역 외 다른 설명/주석/머리말/꼬리말 절대 금지\n'
            '- 영문 고유명사(국가명·기관명·프로젝트명)는 한글 발음 + 괄호 영문 병기 권장. 예: 가나(Ghana)\n\n'
            f'영문:\n{numbered}'
        )

        response = _call_codex(prompt)
        if not response:
            log.warning('translate_batch: codex returned None for chunk %d', chunk_start)
            time.sleep(SLEEP_BETWEEN)
            continue

        # [N] 번역 패턴 파싱 — 응답이 한 줄에 다 들어와도 분리 가능하도록 정규식 전역 매칭
        parsed: dict[int, str] = {}
        # 1) [1] xxx [2] yyy [3] zzz 패턴을 전역 추출
        matches = list(re.finditer(r'\[(\d+)\]\s*', response))
        for i, m in enumerate(matches):
            idx_in_chunk = int(m.group(1)) - 1
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(response)
            translated = response[start:end].strip()
            if 0 <= idx_in_chunk < len(chunk) and translated:
                parsed[idx_in_chunk] = translated

        for idx_in_chunk, (orig_idx, _) in enumerate(chunk):
            if idx_in_chunk in parsed and parsed[idx_in_chunk]:
                out[orig_idx] = parsed[idx_in_chunk]

        time.sleep(SLEEP_BETWEEN)

    return out


def translate_text(text: str) -> str | None:
    """단일 텍스트 번역. 실패 시 None, 빈 입력은 빈 문자열."""
    if not (text or '').strip():
        return ''
    return translate_batch([text])[0]


def translate_notice_fields(rows: list[dict]) -> list[dict]:
    """수집된 공고 dict 들에 title_ko / project_name_ko / notice_text_ko 채워서 반환.

    rows 각 dict 는 최소한 'title' 가 있어야 한다.
    'project_name', 'notice_text' 가 있으면 같이 번역.
    """
    if not rows:
        return rows

    # 번역 대상 평탄화: (row_idx, field, text) 튜플 리스트
    flat: list[tuple[int, str, str]] = []
    for i, r in enumerate(rows):
        # 이미 번역된 row 는 skip (translated_at 이 있고 모든 ko 필드가 채워진 경우)
        if r.get('_skip_translate'):
            continue
        if r.get('title') and not r.get('title_ko'):
            flat.append((i, 'title_ko', r['title']))
        if r.get('project_name') and not r.get('project_name_ko'):
            flat.append((i, 'project_name_ko', r['project_name']))
        if r.get('notice_text') and not r.get('notice_text_ko'):
            flat.append((i, 'notice_text_ko', r['notice_text']))

    if not flat:
        return rows

    texts = [t for _, _, t in flat]
    translations = translate_batch(texts)

    for (idx, field, _), tr in zip(flat, translations):
        if tr is None:
            continue  # 실패 — 원본 dict 의 기존 값 (None) 유지 → 다음 차례 재시도
        rows[idx][field] = tr

    return rows


__all__ = ['translate_batch', 'translate_text', 'translate_notice_fields']
