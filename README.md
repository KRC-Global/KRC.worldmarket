# 발주공고 (MDB Agriculture Tender Dashboard)

WB·ADB·AIIB·AfDB·KOICA·EDCF·JICA 의 **농업분야 발주공고**를 수집·분석하고 대시보드로 보여주는 사이트.

## 구성
- `ingestion/` — Python 수집·분석 파이프라인 (로컬/cron 실행, Supabase 기록)
- `db/schema.sql` — Supabase 스키마 (테이블/뷰/RLS)
- `web/` — Astro + React 사이트 (Vercel 배포)

## 빠른 시작
1. 외부 셋업: [docs/SETUP.md](docs/SETUP.md) 참고 (Supabase·OpenAI 키·Codex 재인증·Hermes 프로필).
2. 시크릿: `cp .env.example .env` 후 값 채우기.
3. DB: Supabase SQL 에디터에 `db/schema.sql` 실행.
4. 수집 테스트(루트에서): `python -m ingestion.pipeline --source worldbank --limit 10 --dry-run`
5. 사이트: `cd web && npm install && npm run dev`

자세한 계획은 승인된 플랜 문서 참조.
