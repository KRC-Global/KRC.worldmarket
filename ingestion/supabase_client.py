"""Supabase 클라이언트 + upsert/Storage 헬퍼."""
from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET_ATTACH = os.environ.get("SUPABASE_BUCKET_ATTACHMENTS", "attachments")
BUCKET_IMAGES = os.environ.get("SUPABASE_BUCKET_IMAGES", "images")

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 가 .env 에 설정되지 않았습니다."
            )
        _client = create_client(SUPABASE_URL, SERVICE_KEY)
    return _client


def upsert_notice(row: dict) -> dict:
    """(source, source_notice_id) 기준 upsert. 반환: 저장된 행."""
    res = (
        get_client()
        .table("notices")
        .upsert(row, on_conflict="source,source_notice_id")
        .execute()
    )
    return res.data[0] if res.data else {}


def insert_attachment(row: dict) -> None:
    get_client().table("attachments").insert(row).execute()


def upload_bytes(bucket: str, path: str, data: bytes, content_type: str) -> str:
    """Storage 업로드 후 public URL 반환."""
    client = get_client()
    client.storage.from_(bucket).upload(
        path, data, {"content-type": content_type, "upsert": "true"}
    )
    return client.storage.from_(bucket).get_public_url(path)


def log_run(source: str, **fields) -> None:
    get_client().table("ingestion_runs").insert({"source": source, **fields}).execute()


# ── 아카이브 수명주기 (sync / cleanup) ───────────────────────────────────────
def fetch_active_notices(source: Optional[str] = None,
                         columns: str = "id,source,source_url,deadline_at,published_at,created_at") -> list[dict]:
    """archived_at is null 인 활성 공고 조회 (source 지정 시 해당 기관만)."""
    q = get_client().table("notices").select(columns).is_("archived_at", "null")
    if source:
        q = q.eq("source", source)
    return q.execute().data or []


def archive_notices(ids: list[str], reason: str) -> int:
    """id 리스트를 archived_at=now, archive_reason=reason 으로 아카이브. 반환: 건수."""
    if not ids:
        return 0
    import datetime as _dt
    now = _dt.datetime.utcnow().isoformat()
    client = get_client()
    done = 0
    for i in range(0, len(ids), 200):  # URL 길이 제한 회피 — 청크 업데이트
        chunk = ids[i:i + 200]
        client.table("notices").update(
            {"archived_at": now, "archive_reason": reason}
        ).in_("id", chunk).execute()
        done += len(chunk)
    return done
