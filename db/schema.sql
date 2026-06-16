-- 발주공고 — Supabase schema
-- Supabase SQL Editor 에 그대로 실행. (idempotent 하게 작성)

-- ─────────────────────────────────────────────
-- Enums
-- ─────────────────────────────────────────────
do $$ begin
  create type mdb_source as enum ('wb','adb','aiib','afdb','koica','edcf','jica');
exception when duplicate_object then null; end $$;

-- ─────────────────────────────────────────────
-- notices : 핵심 공고 테이블
-- ─────────────────────────────────────────────
create table if not exists public.notices (
  id                 uuid primary key default gen_random_uuid(),
  source             mdb_source not null,
  source_notice_id   text not null,           -- 기관 내 공고 고유 id/번호
  title              text not null,
  title_ko           text,                     -- 한국어 제목(번역)
  country            text,
  country_iso        text,                     -- ISO-3166 alpha-2
  sector             text,
  ag_subsector       text,                     -- 관개/축산/수산/농식품 등
  notice_type        text,                     -- IFB / GPN / SPN / Consulting 등
  procurement_method text,
  published_at       timestamptz,
  deadline_at        timestamptz,
  budget_amount      numeric,
  budget_currency    text,
  source_url         text not null,
  raw_text           text,                     -- 공고 원문(+첨부 텍스트 합본)
  language           text,                     -- 원문 언어
  summary            jsonb,                    -- 한국어 구조화 개요(사업명/발주처/규모/마감/자격/핵심요약)
  hero_image_url     text,                     -- gpt-image 일러스트 URL
  content_hash       text,                     -- 본문 해시(보조 중복판정)
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  unique (source, source_notice_id)
);

create index if not exists idx_notices_source       on public.notices (source);
create index if not exists idx_notices_country_iso  on public.notices (country_iso);
create index if not exists idx_notices_deadline      on public.notices (deadline_at);
create index if not exists idx_notices_published      on public.notices (published_at desc);
create index if not exists idx_notices_ag_subsector  on public.notices (ag_subsector);

-- updated_at 자동 갱신
create or replace function public.set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end $$ language plpgsql;

drop trigger if exists trg_notices_updated on public.notices;
create trigger trg_notices_updated before update on public.notices
  for each row execute function public.set_updated_at();

-- ─────────────────────────────────────────────
-- attachments : 첨부문서
-- ─────────────────────────────────────────────
create table if not exists public.attachments (
  id             uuid primary key default gen_random_uuid(),
  notice_id      uuid not null references public.notices(id) on delete cascade,
  filename       text,
  source_url     text,
  storage_path   text,            -- Supabase Storage 경로
  mime           text,
  extracted_text text,
  created_at     timestamptz not null default now()
);
create index if not exists idx_attachments_notice on public.attachments (notice_id);

-- ─────────────────────────────────────────────
-- ingestion_runs : 수집 실행 로그(모니터링)
-- ─────────────────────────────────────────────
create table if not exists public.ingestion_runs (
  id          uuid primary key default gen_random_uuid(),
  source      mdb_source not null,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  found       int default 0,
  inserted    int default 0,
  updated     int default 0,
  errors      int default 0,
  notes       text
);

-- ─────────────────────────────────────────────
-- 대시보드 집계 뷰
-- ─────────────────────────────────────────────
create or replace view public.v_stats_by_mdb as
  select source, count(*) as notice_count,
         count(*) filter (where deadline_at >= now()) as open_count,
         sum(budget_amount) as total_budget
  from public.notices group by source;

create or replace view public.v_stats_by_country as
  select country_iso, country, count(*) as notice_count,
         sum(budget_amount) as total_budget
  from public.notices where country_iso is not null
  group by country_iso, country;

create or replace view public.v_stats_by_sector as
  select coalesce(ag_subsector,'기타') as ag_subsector, count(*) as notice_count
  from public.notices group by coalesce(ag_subsector,'기타');

create or replace view public.v_timeline as
  select date_trunc('month', published_at) as month, source, count(*) as notice_count
  from public.notices where published_at is not null
  group by date_trunc('month', published_at), source;

-- ─────────────────────────────────────────────
-- RLS : anon 읽기 전용, 쓰기는 service_role 만
-- ─────────────────────────────────────────────
alter table public.notices        enable row level security;
alter table public.attachments    enable row level security;
alter table public.ingestion_runs enable row level security;

drop policy if exists anon_read_notices on public.notices;
create policy anon_read_notices on public.notices
  for select to anon, authenticated using (true);

drop policy if exists anon_read_attachments on public.attachments;
create policy anon_read_attachments on public.attachments
  for select to anon, authenticated using (true);

-- ingestion_runs 는 익명에 비공개(정책 없음 = 차단). service_role 은 RLS 우회.

-- 뷰는 security_invoker 로 호출자 권한 적용
alter view public.v_stats_by_mdb     set (security_invoker = true);
alter view public.v_stats_by_country set (security_invoker = true);
alter view public.v_stats_by_sector  set (security_invoker = true);
alter view public.v_timeline         set (security_invoker = true);

-- ─────────────────────────────────────────────
-- Storage 버킷 (대시보드: SQL 로 생성 가능, 실패 시 UI 에서 생성)
-- ─────────────────────────────────────────────
insert into storage.buckets (id, name, public)
  values ('attachments','attachments', true) on conflict (id) do nothing;
insert into storage.buckets (id, name, public)
  values ('images','images', true) on conflict (id) do nothing;
