# 외부 셋업 가이드

코드 스캐폴딩은 끝났고, 아래는 **외부 계정/시크릿이 필요해 직접 하셔야 하는** 단계입니다.

## 1. Supabase
1. https://supabase.com 에서 프로젝트 생성.
2. **SQL Editor** 에 `db/schema.sql` 전체를 붙여넣고 실행 (테이블/뷰/RLS/Storage 버킷 생성).
3. **Settings → API** 에서 값 복사:
   - `Project URL` → `SUPABASE_URL` / `PUBLIC_SUPABASE_URL`
   - `anon public` 키 → `PUBLIC_SUPABASE_ANON_KEY` (웹용, 읽기 전용)
   - `service_role` 키 → `SUPABASE_SERVICE_ROLE_KEY` (수집용, **절대 공개 금지**)
4. Storage 버킷 `attachments`, `images` 가 SQL 로 안 만들어졌으면 UI 에서 public 으로 생성.

## 2. OpenAI 이미지 키 (gpt-image)
- https://platform.openai.com 에서 **API 키 발급** → `OPENAI_API_KEY`.
- Codex OAuth(ChatGPT 로그인)와는 **별개**입니다. gpt-image 는 이 결제용 API 키가 필요합니다.

## 3. 시크릿 파일
```bash
cd 발주공고
cp .env.example .env            # SUPABASE_*, OPENAI_API_KEY 채우기
cp web/.env.example web/.env.local   # PUBLIC_SUPABASE_* 채우기
```

## 4. Codex(OAuth) 재인증 + Hermes 프로필
현재 Codex 토큰이 relogin 필요 상태입니다.
```bash
hermes auth add openai-codex                       # ChatGPT 재로그인
hermes profile create mdb-tender --clone-from openai-codex
# 프로필 config 의 model 을 openai-codex / gpt-5.5 로 설정 (lmstudio 오버라이드 해제)
hermes profile show mdb-tender
```
이 프로젝트 폴더에서 Hermes 를 실행하면 `AGENTS.md` 가 자동 주입됩니다.

## 5. 수집 파이프라인 (로컬)
```bash
cd 발주공고
/opt/homebrew/bin/python3.12 -m venv ingestion/.venv
ingestion/.venv/bin/pip install -r ingestion/requirements.txt
# 먼저 네트워크만 확인(DB 기록 없음):
ingestion/.venv/bin/python -m ingestion.pipeline --source wb --limit 5 --dry-run
# 실제 적재(요약/이미지 생략하고 먼저 적재만):
ingestion/.venv/bin/python -m ingestion.pipeline --source wb --limit 10 --no-illustrate
```
> RSS 피드 URL(adb/afdb/aiib)은 실제 주소 확인 후 `collectors/*.py` 의 `FEEDS` 를 갱신해야 할 수 있습니다.
> KOICA·EDCF·JICA 스크래퍼는 M2 단계에서 구현 예정(현재 NotImplementedError).

## 6. 웹 (로컬 → Vercel)
```bash
cd 발주공고/web
npm install
npm run dev          # http://localhost:4321
```
Vercel: GitHub 저장소 연결 → 환경변수 `PUBLIC_SUPABASE_URL`, `PUBLIC_SUPABASE_ANON_KEY` 등록 → 배포.

> ⚠️ **Google Drive 주의**: 이 폴더가 Drive 동기화 경로 안이라 `node_modules`/`.venv` 가 동기화되면
> 충돌·성능 저하가 생깁니다. `.gitignore` 로 git 에서는 제외되지만, Drive 동기화 자체는 별도입니다.
> 가능하면 로컬 비동기화 경로에 clone 해서 개발하거나, 개발 중 Drive 동기화를 일시중지하세요.

## 7. 매일 자동 수집 (cron)
```bash
hermes cron create daily-mdb-tender \
  --cron "0 2 * * *" \
  --profile mdb-tender \
  --workdir "<발주공고 절대경로>" \
  --message "ingestion.venv 의 python 으로 'python -m ingestion.pipeline --source all' 실행하고 결과 요약"
```
(정확한 `hermes cron create` 옵션은 `hermes cron --help` 로 확인 후 맞추세요.)
