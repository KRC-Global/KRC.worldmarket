import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.PUBLIC_SUPABASE_URL;
const anon = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

/**
 * env(PUBLIC_SUPABASE_URL / PUBLIC_SUPABASE_ANON_KEY) 가 없으면 supabase-js 의
 * createClient 가 throw → SSR 페이지가 전부 500 이 된다. Supabase 셋업 전에도
 * UI 가 빈 데이터로 렌더되도록, env 가 없을 때는 안전한 스텁 클라이언트를 쓴다.
 * env 가 채워지면 실제 클라이언트로 자동 전환된다(스텁은 영향 없음).
 */
function makeStub() {
  const builder: any = {};
  const state = { single: false };
  const result = () => ({ data: state.single ? null : [], count: 0, error: null });
  const ret = () => builder;
  for (const m of [
    "select", "eq", "neq", "gte", "lte", "gt", "lt", "in", "or", "ilike",
    "like", "order", "limit", "range", "contains", "filter", "match", "not",
  ]) {
    builder[m] = ret;
  }
  builder.single = () => { state.single = true; return builder; };
  builder.maybeSingle = () => { state.single = true; return builder; };
  builder.then = (resolve: (v: any) => void) => resolve(result());
  return { from: () => builder } as any;
}

if (!url || !anon) {
  console.warn("[supabase] PUBLIC_SUPABASE_URL / PUBLIC_SUPABASE_ANON_KEY 미설정 — 빈 데이터 스텁으로 동작 (Supabase 셋업 후 env 등록 시 실데이터)");
}

// anon 키 + RLS(읽기 전용). 서버(SSR)·클라이언트 양쪽에서 사용.
export const supabase: any = url && anon ? createClient(url, anon) : makeStub();
