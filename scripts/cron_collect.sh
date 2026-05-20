#!/bin/zsh
# KRC World Market — 매일 자동 수집 + 한글 번역 진입점
# launchd 가 호출. 모든 stdout/stderr 는 logs/collect-YYYYMMDD.log 에 기록.

set -u

PROJECT_ROOT="/Volumes/문서/글로벌사업처/KRC.worldmarket"
VENV_PY="$HOME/.venvs/krc-worldmarket/bin/python"
LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/collect-$(date +%Y%m%d).log"

# codex CLI · 기타 도구 경로 보장 (launchd 의 빈약한 PATH 보완)
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

mkdir -p "$LOG_DIR"

{
  echo "==== KRC collect run $(date '+%Y-%m-%d %H:%M:%S %Z') ===="
  echo "project_root=$PROJECT_ROOT"
  echo "python=$VENV_PY"
  echo "codex=$(command -v codex || echo 'NOT FOUND')"

  if [ ! -x "$VENV_PY" ]; then
    echo "ERROR: venv python not found at $VENV_PY" >&2
    exit 2
  fi

  cd "$PROJECT_ROOT" || exit 3
  "$VENV_PY" scripts/run_collect_direct.py
  rc=$?
  echo "==== exit_code=$rc ===="
  exit $rc
} >> "$LOG_FILE" 2>&1
