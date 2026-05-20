/**
 * KRC World Market — Supabase 공유 클라이언트 모듈
 *
 * 담당:
 *   1. Supabase 클라이언트 싱글턴 초기화
 *   2. 인증 상태 관리 (Google OAuth)
 *   3. 헤더 인증 UI 렌더링 (로그인 버튼 / 아바타 / 로그아웃)
 *   4. 방문자 추적 (page_views, notice_views, search_events)
 *   5. 북마크 관리 (notice_bookmarks)
 *   6. Flask API 호출용 JWT 토큰 제공
 *
 * 사용법: <script type="module" src="/assets/js/supabase-client.js"></script>
 */

import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm';

// ── 설정 ───────────────────────────────────────────────────────────────────────
const SUPABASE_URL      = 'https://pvmhqxcjcxhltuholhlp.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InB2bWhxeGNqY3hobHR1aG9saGxwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg1MTkzODIsImV4cCI6MjA5NDA5NTM4Mn0.RYxdqf2hDYdpnZje9iUmnNVov1jy6ucY3L5CjXtOBg0';

export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ── 세션 / 인증 ────────────────────────────────────────────────────────────────

/** 현재 세션 반환 (없으면 null). */
export async function getSession() {
  const { data } = await supabase.auth.getSession();
  return data.session ?? null;
}

/** Flask 관리자 API 호출용 JWT 액세스 토큰 반환. */
export async function getAdminToken() {
  const session = await getSession();
  return session?.access_token ?? null;
}

/** app_metadata.role === 'admin' 여부. JWT에서 읽으므로 서버측 검증과 동일. */
export function isAdmin(session) {
  return session?.user?.app_metadata?.role === 'admin';
}

/** Google OAuth 로그인 시작. 완료 후 현재 페이지로 리디렉트. */
export async function signInWithGoogle() {
  const { error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: { redirectTo: window.location.origin + window.location.pathname },
  });
  if (error) console.error('[KRC Auth] 로그인 오류:', error.message);
}

/** 로그아웃. */
export async function signOut() {
  await supabase.auth.signOut();
  location.reload();
}

// ── 헤더 인증 UI ──────────────────────────────────────────────────────────────

/**
 * 네비게이션 컨테이너에 인증 UI를 렌더링한다.
 *
 * @param {HTMLElement} navEl - 인증 요소를 삽입할 <nav> 엘리먼트
 * @param {object}      opts
 * @param {boolean}     opts.showAdminLink     - 관리자일 때 admin.html 링크 표시
 * @param {boolean}     opts.showAnalyticsLink - 관리자일 때 analytics.html 링크 표시
 */
export async function renderAuthUI(navEl, opts = {}) {
  if (!navEl) return;
  const session = await getSession();

  if (!session) {
    // 미로그인 — 구글 로그인 버튼
    const btn = document.createElement('button');
    btn.className = 'nav-link auth-login-btn';
    btn.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);border-radius:6px;padding:5px 12px;color:#fff;font-size:13px;font-weight:500;';
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>Google로 로그인`;
    btn.addEventListener('click', signInWithGoogle);
    navEl.appendChild(btn);
    return;
  }

  const user  = session.user;
  const admin = isAdmin(session);

  // 관리자 전용 링크
  if (admin && opts.showAdminLink) {
    const a = _makeNavLink('/admin.html', '관리자');
    if (window.location.pathname.includes('admin.html')) a.classList.add('active');
    navEl.appendChild(a);
  }
  if (admin && opts.showAnalyticsLink) {
    const a = _makeNavLink('/analytics.html', '애널리틱스');
    if (window.location.pathname.includes('analytics.html')) a.classList.add('active');
    navEl.appendChild(a);
  }

  // 유저 정보 + 로그아웃
  const pill = document.createElement('div');
  pill.className = 'auth-user-pill';
  pill.style.cssText = 'display:flex;align-items:center;gap:8px;';

  const avatarUrl = user.user_metadata?.avatar_url || '';
  const name      = user.user_metadata?.full_name || user.email || '';

  pill.innerHTML = `
    ${avatarUrl ? `<img src="${avatarUrl}" alt="" style="width:28px;height:28px;border-radius:50%;border:2px solid rgba(255,255,255,.4);object-fit:cover;">` : ''}
    <span style="font-size:13px;color:#fff;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${name}">${name}</span>
    <button class="auth-logout-btn" style="background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.3);border-radius:6px;padding:4px 10px;color:#fff;font-size:12px;cursor:pointer;">로그아웃</button>
  `;
  pill.querySelector('.auth-logout-btn').addEventListener('click', signOut);
  navEl.appendChild(pill);
}

function _makeNavLink(href, text) {
  const a = document.createElement('a');
  a.href = href;
  a.className = 'nav-link';
  a.textContent = text;
  return a;
}

// ── 세션 변경 감지 ─────────────────────────────────────────────────────────────
supabase.auth.onAuthStateChange((_event, _session) => {
  // 필요 시 각 페이지에서 onAuthChange()로 구독
});

export function onAuthChange(callback) {
  return supabase.auth.onAuthStateChange(callback);
}

// ── 방문자 추적 ────────────────────────────────────────────────────────────────

function _getSessionId() {
  let sid = sessionStorage.getItem('krc_sid');
  if (!sid) {
    sid = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
    sessionStorage.setItem('krc_sid', sid);
  }
  return sid;
}

/** 페이지뷰 기록. */
export async function trackPageView(path) {
  try {
    const session = await getSession();
    await supabase.from('page_views').insert({
      path:       path || window.location.pathname,
      session_id: _getSessionId(),
      user_id:    session?.user?.id ?? null,
      referrer:   document.referrer || null,
    });
  } catch (_) { /* 추적 실패는 무시 */ }
}

/** 공고 뷰 기록. source = 'map' | 'list' | 'direct' */
export async function trackNoticeView(noticeId, source = 'list') {
  try {
    const session = await getSession();
    await supabase.from('notice_views').insert({
      notice_id:  noticeId,
      session_id: _getSessionId(),
      user_id:    session?.user?.id ?? null,
      source,
    });
  } catch (_) { /* 추적 실패는 무시 */ }
}

/** 검색 이벤트 기록. */
export async function trackSearch(query, sourceFilter, resultsCount) {
  try {
    const session = await getSession();
    await supabase.from('search_events').insert({
      query:         query || null,
      source_filter: sourceFilter || null,
      results_count: resultsCount ?? null,
      session_id:    _getSessionId(),
      user_id:       session?.user?.id ?? null,
    });
  } catch (_) { /* 추적 실패는 무시 */ }
}

// ── 북마크 ─────────────────────────────────────────────────────────────────────

/** 현재 유저의 북마크 notice_id Set 반환. 미로그인 시 빈 Set. */
export async function loadUserBookmarks() {
  const session = await getSession();
  if (!session) return new Set();
  const { data } = await supabase
    .from('notice_bookmarks')
    .select('notice_id')
    .eq('user_id', session.user.id);
  return new Set((data || []).map(r => r.notice_id));
}

/**
 * 북마크 토글.
 * @param {number}  noticeId
 * @param {boolean} isBookmarked - 현재 북마크 상태
 * @returns {boolean} 새 북마크 상태 (true = 추가됨, false = 제거됨)
 */
export async function toggleBookmark(noticeId, isBookmarked) {
  const session = await getSession();
  if (!session) {
    // 미로그인 → 로그인 유도
    signInWithGoogle();
    return isBookmarked;
  }
  if (isBookmarked) {
    await supabase.from('notice_bookmarks')
      .delete()
      .eq('user_id', session.user.id)
      .eq('notice_id', noticeId);
    return false;
  } else {
    await supabase.from('notice_bookmarks')
      .insert({ user_id: session.user.id, notice_id: noticeId });
    return true;
  }
}
