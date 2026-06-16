export type MdbSource = "wb" | "adb" | "aiib" | "afdb" | "koica" | "edcf" | "jica";

export const MDB_LABELS: Record<MdbSource, string> = {
  wb: "World Bank",
  adb: "ADB",
  aiib: "AIIB",
  afdb: "AfDB",
  koica: "KOICA",
  edcf: "EDCF",
  jica: "JICA",
};

export interface NoticeSummary {
  사업명?: string;
  발주처?: string;
  국가?: string;
  분야?: string;
  규모?: string;
  마감일?: string;
  자격요건?: string;
  핵심요약?: string;
}

export interface Notice {
  id: string;
  source: MdbSource;
  source_notice_id: string;
  title: string;
  title_ko: string | null;
  country: string | null;
  country_iso: string | null;
  sector: string | null;
  ag_subsector: string | null;
  notice_type: string | null;
  published_at: string | null;
  deadline_at: string | null;
  budget_amount: number | null;
  budget_currency: string | null;
  source_url: string;
  raw_text: string | null;
  summary: NoticeSummary | null;
  hero_image_url: string | null;
}
