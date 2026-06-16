# 발주공고 — MDB 농업분야 발주공고 수집·분석 대시보드

이 파일은 Hermes 에이전트가 이 프로젝트 디렉터리에서 작업할 때 자동 주입되는 규칙이다.

## 목표
WB·ADB·AIIB·AfDB·KOICA·EDCF·JICA 가 발주하는 **농업분야** 프로젝트 공고를 수집·분석하여
사업별·국가별·MDB별 현황을 대시보드로 보여주는 사이트를 구축·운영한다.

## 아키텍처
- **수집/분석/이미지**: 로컬에서 `ingestion/` 파이프라인(Python)이 수행 → Supabase 에 기록.
- **DB/스토리지**: Supabase (Postgres + Storage).
- **사이트**: `web/` Astro + React 아일랜드, Vercel SSR 배포, Supabase 를 실시간 읽기.
- **자동화**: 매일 cron 으로 `ingestion/pipeline.py` 실행.
- **LLM**: OpenAI Codex(OAuth) — 이 프로필(`mdb-tender`)의 기본 모델.

## 데이터 소스
| 기관 | 방식 | 대상 |
|---|---|---|
| WB | REST API | https://search.worldbank.org/api/procnotices |
| ADB | RSS | https://www.adb.org/rss |
| AfDB | RSS | https://www.afdb.org/en/rss-feeds |
| AIIB | RSS/Excel/scrape | aiib.org project-procurement |
| KOICA | scrape(browser) | nebid.koica.go.kr |
| EDCF | scrape(KONEPS) | g2b.go.kr / koneps.go.kr |
| JICA | scrape(국가별) | jica.go.jp tender + 국가사무소 |

UN Development Business 는 2025-03 폐쇄 — 사용 금지.

## 농업 필터 키워드 (다국어)
EN: agriculture, agri, agribusiness, irrigation, rural, livestock, fisheries, aquaculture, food security, crop, horticulture, agro, agroforestry, farming
KO: 농업, 관개, 축산, 수산, 농촌, 식량, 농식품
JA: 農業, 灌漑, 農村, 漁業
FR: agriculture, irrigation, élevage, pêche, rural

## 공통 데이터 스키마
`notices` 테이블 컬럼은 `db/schema.sql` 을 단일 진실원으로 삼는다. 수집기는 반드시
`(source, source_notice_id)` 를 채워 중복을 방지하고, 본문은 `raw_text`, 한국어 개요는
`summary`(jsonb) 에 넣는다. 자세한 컬럼은 schema.sql 참조.

## 코딩 규칙
- 비밀키는 `.env`(수집)·Vercel 환경변수(웹)에만. 코드/커밋에 절대 하드코딩 금지.
- 수집기는 기관별로 `ingestion/collectors/<mdb>.py` 한 파일, 공통 출력은 `normalize.py` 의 dict 스키마를 따른다.
- 스크래핑은 요청 간격(rate limit)·robots/ToS 준수. WB 데이터는 CC-BY 4.0 출처 표기.
- 웹은 Supabase anon 키 + RLS(읽기 전용)만 사용. service_role 키는 절대 클라이언트에 노출 금지.

## 검증
새 수집기는 루트에서 `python -m ingestion.pipeline --source <mdb> --limit 10` 으로 적재 확인 후 통합.
