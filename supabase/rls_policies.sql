-- ============================================================
-- KRC World Market — Supabase RLS 정책
-- Supabase Dashboard > SQL Editor 에서 실행하세요.
-- 이미 적용된 정책이 있으면 DROP POLICY 후 재생성됩니다.
-- ============================================================


-- ── 1. notice_bookmarks ──────────────────────────────────────
-- 로그인한 사용자가 자신의 북마크만 읽기/쓰기/삭제 가능.

ALTER TABLE notice_bookmarks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "bookmarks: own select"  ON notice_bookmarks;
DROP POLICY IF EXISTS "bookmarks: own insert"  ON notice_bookmarks;
DROP POLICY IF EXISTS "bookmarks: own delete"  ON notice_bookmarks;

CREATE POLICY "bookmarks: own select"
  ON notice_bookmarks FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "bookmarks: own insert"
  ON notice_bookmarks FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "bookmarks: own delete"
  ON notice_bookmarks FOR DELETE
  USING (auth.uid() = user_id);


-- ── 2. page_views ────────────────────────────────────────────
-- 누구나 INSERT 가능 (방문자 추적).
-- SELECT 는 admin 역할만 허용 (analytics.html 전용).

ALTER TABLE page_views ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "page_views: insert"        ON page_views;
DROP POLICY IF EXISTS "page_views: admin select"  ON page_views;

CREATE POLICY "page_views: insert"
  ON page_views FOR INSERT
  WITH CHECK (true);

CREATE POLICY "page_views: admin select"
  ON page_views FOR SELECT
  USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
  );


-- ── 3. notice_views ──────────────────────────────────────────
-- 누구나 INSERT, admin만 SELECT.

ALTER TABLE notice_views ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "notice_views: insert"        ON notice_views;
DROP POLICY IF EXISTS "notice_views: admin select"  ON notice_views;

CREATE POLICY "notice_views: insert"
  ON notice_views FOR INSERT
  WITH CHECK (true);

CREATE POLICY "notice_views: admin select"
  ON notice_views FOR SELECT
  USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
  );


-- ── 4. search_events ─────────────────────────────────────────
-- 누구나 INSERT, admin만 SELECT.

ALTER TABLE search_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "search_events: insert"        ON search_events;
DROP POLICY IF EXISTS "search_events: admin select"  ON search_events;

CREATE POLICY "search_events: insert"
  ON search_events FOR INSERT
  WITH CHECK (true);

CREATE POLICY "search_events: admin select"
  ON search_events FOR SELECT
  USING (
    (auth.jwt() -> 'app_metadata' ->> 'role') = 'admin'
  );
