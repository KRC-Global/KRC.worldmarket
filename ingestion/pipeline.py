"""수집·분석 오케스트레이터.

실행 (프로젝트 루트 = 발주공고/ 에서):
    python -m ingestion.pipeline --source worldbank --limit 10
    python -m ingestion.pipeline --source all
옵션:
    --no-analyze     : Codex 요약 생략
    --no-illustrate  : gpt-image 일러스트 생략
    --dry-run        : Supabase 기록 없이 콘솔 출력만
"""
from __future__ import annotations

import argparse
import sys
import traceback

from . import analyze, illustrate
from .collectors import ALL_SOURCES, REGISTRY

# source 별칭
ALIASES = {"worldbank": "wb", "world_bank": "wb"}


def run_source(source: str, limit: int, do_analyze: bool, do_illustrate: bool, dry: bool) -> dict:
    source = ALIASES.get(source, source)
    if source not in REGISTRY:
        raise SystemExit(f"알 수 없는 source: {source} (가능: {ALL_SOURCES})")

    print(f"\n=== [{source}] 수집 시작 (limit={limit}) ===")
    stats = {"found": 0, "inserted": 0, "errors": 0}
    try:
        rows = REGISTRY[source](limit)
    except NotImplementedError as e:
        print(f"  미구현: {e}")
        return stats
    stats["found"] = len(rows)
    print(f"  농업 필터 통과: {len(rows)}건")

    if dry:
        for r in rows[:5]:
            print(f"   - {r['title'][:80]}  ({r.get('country') or '-'})")
        return stats

    from . import supabase_client  # 지연 임포트(키 없을 때 dry-run 가능하도록)

    for r in rows:
        try:
            if do_analyze:
                r["summary"] = analyze.summarize(r)
            saved = supabase_client.upsert_notice(r)
            if do_illustrate and saved and not saved.get("hero_image_url"):
                url = illustrate.generate({**r, "summary": r.get("summary")})
                if url:
                    supabase_client.upsert_notice({**r, "hero_image_url": url})
            stats["inserted"] += 1
        except Exception:  # noqa: BLE001
            stats["errors"] += 1
            traceback.print_exc()

    supabase_client.log_run(source, **stats, finished_at="now()")
    print(f"  적재 {stats['inserted']}건, 에러 {stats['errors']}건")
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MDB 농업 발주공고 수집 파이프라인")
    p.add_argument("--source", default="all", help="wb|adb|afdb|aiib|koica|edcf|jica|all")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--no-analyze", action="store_true")
    p.add_argument("--no-illustrate", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    sources = ALL_SOURCES if args.source == "all" else [args.source]
    total = {"found": 0, "inserted": 0, "errors": 0}
    for s in sources:
        st = run_source(
            s, args.limit, not args.no_analyze, not args.no_illustrate, args.dry_run
        )
        for k in total:
            total[k] += st.get(k, 0)

    print(f"\n=== 합계: found={total['found']} inserted={total['inserted']} errors={total['errors']} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
