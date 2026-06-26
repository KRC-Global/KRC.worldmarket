"""수집·분석 오케스트레이터.

실행 (프로젝트 루트 = 발주공고/ 에서):
    python -m ingestion.pipeline --source worldbank --limit 10
    python -m ingestion.pipeline --source all
옵션:
    --no-analyze     : Codex 요약 생략
    --no-illustrate  : gpt-image 일러스트 생략
    --no-sync        : 수집 후 아카이브 동기화/정리 생략 (--source all 일 때만 기본 동작)
    --dry-run        : Supabase 기록 없이 콘솔 출력만
"""
from __future__ import annotations

import argparse
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import analyze, illustrate
from .collectors import ALL_SOURCES, REGISTRY
from .collectors import _mdb_common as C

# source 별칭
ALIASES = {"worldbank": "wb", "world_bank": "wb"}

DEFAULT_FRESHNESS_DAYS = C.DEFAULT_FRESHNESS_DAYS


# ── 수집 (병렬) ──────────────────────────────────────────────────────────────
def collect_phase(sources: list[str], limit: int) -> tuple[dict, dict]:
    """sources 를 병렬 수집. 반환: (rows_by_source, errors_by_source)."""
    rows_by_source: dict[str, list] = {}
    errors: dict[str, str] = {}

    def _one(src: str):
        return src, REGISTRY[src](limit)

    if len(sources) == 1:
        src = sources[0]
        try:
            rows_by_source[src] = REGISTRY[src](limit)
        except NotImplementedError as e:
            print(f"  [{src}] 미구현: {e}")
            rows_by_source[src] = []
        except Exception as e:  # noqa: BLE001
            errors[src] = str(e)
            rows_by_source[src] = []
            traceback.print_exc()
        return rows_by_source, errors

    with ThreadPoolExecutor(max_workers=min(5, len(sources))) as ex:
        futures = {ex.submit(_one, s): s for s in sources}
        for fut in as_completed(futures):
            src = futures[fut]
            try:
                _, rows = fut.result()
                rows_by_source[src] = rows
                print(f"  [{src}] fetched {len(rows)}건")
            except NotImplementedError as e:
                print(f"  [{src}] 미구현: {e}")
                rows_by_source[src] = []
            except Exception as e:  # noqa: BLE001
                errors[src] = str(e)
                rows_by_source[src] = []
                print(f"  [{src}] 실패 — {e}")
    return rows_by_source, errors


# ── 배치 내 중복 제거 (URL + 정규화 title/country) ───────────────────────────
def dedupe_batch(rows_by_source: dict) -> list[dict]:
    """여러 소스 결과를 합치며 URL/(정규화 title, country) 중복을 제거.
    서로 다른 기관이 같은 사업을 공고한 경우도 1건으로 수렴 (먼저 온 것 유지)."""
    seen_urls: set[str] = set()
    seen_fp: set[tuple] = set()
    merged: list[dict] = []
    for src in REGISTRY:  # 안정적 우선순위 (등록 순서)
        for r in rows_by_source.get(src, []):
            url = r.get("source_url") or ""
            fp = (C.normalize_title(r.get("title") or ""),
                  C.normalize_country_key(r.get("country") or ""))
            if url and url in seen_urls:
                continue
            if fp[0] and fp in seen_fp:
                continue
            if url:
                seen_urls.add(url)
            if fp[0]:
                seen_fp.add(fp)
            merged.append(r)
    return merged


# ── 처리 (분석/적재/일러스트) ────────────────────────────────────────────────
def process_rows(rows: list[dict], do_analyze: bool, do_illustrate: bool) -> dict:
    from . import supabase_client

    stats = {"inserted": 0, "errors": 0}
    for r in rows:
        try:
            if do_analyze:
                r["summary"] = analyze.summarize(r)
            saved = supabase_client.upsert_notice(_strip_internal(r))
            if do_illustrate and saved and not saved.get("hero_image_url"):
                url = illustrate.generate({**r, "summary": r.get("summary")})
                if url:
                    supabase_client.upsert_notice({**_strip_internal(r), "hero_image_url": url})
            stats["inserted"] += 1
        except Exception:  # noqa: BLE001
            stats["errors"] += 1
            traceback.print_exc()
    return stats


def _strip_internal(row: dict) -> dict:
    """notices 컬럼이 아닌 보조 키(_로 시작) 제거."""
    return {k: v for k, v in row.items() if not k.startswith("_")}


# ── 아카이브 동기화 / 정리 ───────────────────────────────────────────────────
def sync_and_cleanup(fetched_urls_by_source: dict, errors: dict, days: int) -> dict:
    """① 이번 수집에 없는 기존 활성 레코드 아카이브(소스별, 안전장치 포함)
       ② 마감/노후 레코드 아카이브.
    안전장치: 에러난 소스 / 0건 소스는 건드리지 않음(일시 장애로 인한 오삭제 방지)."""
    from datetime import datetime, timedelta

    from . import supabase_client

    archived_removed = 0
    synced, skipped = [], []
    for src, urls in fetched_urls_by_source.items():
        if src in errors:
            skipped.append(f"{src}(error)")
            continue
        if not urls:
            skipped.append(f"{src}(0건)")
            continue
        active = supabase_client.fetch_active_notices(source=src, columns="id,source_url")
        to_archive = [n["id"] for n in active if n.get("source_url") not in urls]
        if to_archive:
            archived_removed += supabase_client.archive_notices(to_archive, "source_removed")
            print(f"  [sync] {src}: {len(to_archive)}건 아카이브(source_removed)")
        synced.append(src)

    # 마감/노후 정리 — 전 소스 활성 레코드 대상
    cutoff = (datetime.utcnow() - timedelta(days=days)).date()
    today = datetime.utcnow().date()
    active_all = supabase_client.fetch_active_notices(
        columns="id,deadline_at,published_at,created_at")
    by_deadline, by_age = [], []
    for n in active_all:
        dl = C.parse_date_any(n.get("deadline_at") or "")
        if dl and dl < today:
            by_deadline.append(n["id"])
            continue
        posted = C.parse_date_any(n.get("published_at") or n.get("created_at") or "")
        if posted and posted < cutoff:
            by_age.append(n["id"])
    archived_deadline = supabase_client.archive_notices(by_deadline, "deadline_passed")
    archived_age = supabase_client.archive_notices(by_age, "aged_out")

    result = {
        "archived_source_removed": archived_removed,
        "archived_deadline_passed": archived_deadline,
        "archived_aged_out": archived_age,
        "synced_sources": synced,
        "skipped_sources": skipped,
    }
    print(f"  [cleanup] {result}")
    return result


# ── 메인 ─────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="MDB 농업 발주공고 수집 파이프라인")
    p.add_argument("--source", default="all", help="wb|adb|afdb|aiib|isdb|ungm|koica|edcf|jica|all")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--no-analyze", action="store_true")
    p.add_argument("--no-illustrate", action="store_true")
    p.add_argument("--no-sync", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    if args.source == "all":
        sources = ALL_SOURCES
    else:
        src = ALIASES.get(args.source, args.source)
        if src not in REGISTRY:
            raise SystemExit(f"알 수 없는 source: {src} (가능: {ALL_SOURCES})")
        sources = [src]

    print(f"\n=== 수집 시작: {', '.join(sources)} (limit={args.limit}) ===")
    rows_by_source, errors = collect_phase(sources, args.limit)

    # sync 용 — 소스별 수집 URL (배치 중복제거 이전 기준)
    fetched_urls_by_source = {
        src: {r.get("source_url") for r in rows if r.get("source_url")}
        for src, rows in rows_by_source.items()
    }

    merged = dedupe_batch(rows_by_source)
    found = sum(len(v) for v in rows_by_source.values())
    print(f"  수집 {found}건 → 중복제거 후 {len(merged)}건"
          + (f" | 에러: {errors}" if errors else ""))

    if args.dry_run:
        for r in merged[:10]:
            print(f"   - [{r['source']}] {r['title'][:72]}  ({r.get('country') or '-'})")
        print(f"\n=== dry-run 종료: found={found} deduped={len(merged)} ===")
        return 0

    stats = process_rows(merged, not args.no_analyze, not args.no_illustrate)

    from datetime import datetime

    from . import supabase_client
    finished = datetime.utcnow().isoformat()
    for src in sources:
        supabase_client.log_run(
            src, found=len(rows_by_source.get(src, [])),
            inserted=sum(1 for r in merged if r["source"] == src),
            errors=1 if src in errors else 0, finished_at=finished,
        )

    # 아카이브 동기화/정리 — all 수집 + sync 활성화 시
    if not args.no_sync and args.source == "all":
        sync_and_cleanup(fetched_urls_by_source, errors, days=DEFAULT_FRESHNESS_DAYS)

    print(f"\n=== 완료: found={found} deduped={len(merged)} "
          f"inserted={stats['inserted']} errors={stats['errors']} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
