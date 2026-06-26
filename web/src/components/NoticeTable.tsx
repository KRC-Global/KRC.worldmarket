import { useEffect, useMemo, useState } from "react";
import { supabase } from "../lib/supabase";
import { MDB_LABELS, type MdbSource, type Notice } from "../types";

const SOURCES = Object.keys(MDB_LABELS) as MdbSource[];

// 기관별 Slack 카테고리 색 (배지 좌측 점)
const SRC_COLOR: Record<MdbSource, string> = {
  wb: "#36c5f0", adb: "#2eb67d", aiib: "#ecb22e", afdb: "#e01e5a",
  koica: "#b07fca", edcf: "#1ab9ff", jica: "#cda4d6",
};

export default function NoticeTable() {
  const [rows, setRows] = useState<Notice[]>([]);
  const [q, setQ] = useState("");
  const [src, setSrc] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      let query = supabase
        .from("notices")
        .select("id,source,title,country,ag_subsector,deadline_at,published_at,source_url")
        .order("published_at", { ascending: false })
        .limit(300);
      if (src) query = query.eq("source", src);
      const { data } = await query;
      setRows((data as Notice[]) ?? []);
      setLoading(false);
    })();
  }, [src]);

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return rows;
    return rows.filter((r) =>
      [r.title, r.country, r.ag_subsector].some((v) => (v ?? "").toLowerCase().includes(t))
    );
  }, [rows, q]);

  return (
    <div>
      <div style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap" }}>
        <input
          className="field"
          placeholder="제목 · 국가 · 분야 검색"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="공고 검색"
          style={{ flex: "1 1 260px", minWidth: 0 }}
        />
        <select className="field" value={src} onChange={(e) => setSrc(e.target.value)} aria-label="기관 필터">
          <option value="">전체 기관</option>
          {SOURCES.map((s) => <option key={s} value={s}>{MDB_LABELS[s]}</option>)}
        </select>
      </div>

      {loading ? (
        <Skeleton />
      ) : filtered.length === 0 ? (
        <Empty hasQuery={q.trim().length > 0 || src.length > 0} />
      ) : (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="data">
            <thead>
              <tr>
                <th>기관</th><th>제목</th><th>국가</th><th>분야</th><th>마감</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td>
                    <span className="badge" style={{ color: SRC_COLOR[r.source], borderColor: "transparent", background: "rgb(255 255 255 / .04)" }}>
                      <span className="dot" /> {MDB_LABELS[r.source]}
                    </span>
                  </td>
                  <td><a className="link" href={`/notices/${r.id}`} style={{ fontWeight: 550 }}>{r.title}</a></td>
                  <td className="muted">{r.country ?? "-"}</td>
                  <td className="muted">{r.ag_subsector ?? "-"}</td>
                  <td style={{ fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap" }}>{r.deadline_at?.slice(0, 10) ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && filtered.length > 0 && (
        <p className="faint" style={{ fontSize: 13, marginTop: 12 }}>{filtered.length}건</p>
      )}
    </div>
  );
}

function Skeleton() {
  return (
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      <style>{`@media (prefers-reduced-motion:no-preference){.sk{animation:shimmer 1.3s ease-in-out infinite}}@keyframes shimmer{0%,100%{opacity:.5}50%{opacity:.85}}`}</style>
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} style={{ display: "flex", gap: 16, padding: "14px 12px", borderBottom: i < 7 ? "1px solid var(--line-soft)" : "none" }}>
          <Bar w={84} /><Bar w="40%" /><Bar w={70} /><Bar w={90} /><Bar w={74} />
        </div>
      ))}
    </div>
  );
}

function Bar({ w }: { w: number | string }) {
  return <span className="sk" style={{ height: 12, width: w, borderRadius: 6, background: "var(--surface-hover)", display: "inline-block" }} />;
}

function Empty({ hasQuery }: { hasQuery: boolean }) {
  return (
    <div className="card" style={{ display: "grid", placeItems: "center", textAlign: "center", padding: "56px 20px", gap: 8 }}>
      <div style={{ fontSize: 15, fontWeight: 600 }}>{hasQuery ? "검색 결과가 없습니다" : "표시할 공고가 없습니다"}</div>
      <p className="muted" style={{ fontSize: 13, margin: 0 }}>
        {hasQuery ? "검색어나 기관 필터를 바꿔보세요." : "수집 파이프라인 실행 후 공고가 채워집니다."}
      </p>
    </div>
  );
}
