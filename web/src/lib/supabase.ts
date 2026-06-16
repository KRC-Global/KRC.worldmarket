import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.PUBLIC_SUPABASE_URL;
const anon = import.meta.env.PUBLIC_SUPABASE_ANON_KEY;

if (!url || !anon) {
  // 빌드/개발 시 친절한 안내
  console.warn("[supabase] PUBLIC_SUPABASE_URL / PUBLIC_SUPABASE_ANON_KEY 미설정 (.env.local 확인)");
}

// anon 키 + RLS(읽기 전용). 서버(SSR)·클라이언트 양쪽에서 사용.
export const supabase = createClient(url ?? "", anon ?? "");
