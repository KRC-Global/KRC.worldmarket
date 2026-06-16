import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import vercel from "@astrojs/vercel/serverless";

// SSR (Vercel) — Supabase 를 실시간으로 읽어 매일 갱신된 데이터를 재배포 없이 반영
export default defineConfig({
  output: "server",
  adapter: vercel(),
  integrations: [react()],
});
