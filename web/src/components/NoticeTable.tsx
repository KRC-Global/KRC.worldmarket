import { useEffect, useMemo, useState } from "react";
import { supabase } from "../lib/supabase";
import { MDB_LABELS, type MdbSource, type Notice } from "../types";

const SOURCES = Object.keys(MDB_LABELS) as MdbSource[];

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
      <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>
        <input
          placeholder="제목·국가·분야 검색"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={inputStyle}
        />
        <select value={src} onChange={(e) => setSrc(e.target.value)} style={inputStyle}>
          <option value="">전체 기관</option>
          {SOURCES.map((s) => <option key={s} value={s}>{MDB_LABELS[s]}</option>)}
        </select>
      </div>
      {loading ? <p>불러오는 중…</p> : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", color: "#9aa3b2" }}>
              <th style={th}>기관</th><th style={th}>제목</th><th style={th}>국가</th>
              <th style={th}>분야</th><th style={th}>마감</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr key={r.id} style={{ borderTop: "1px solid #272b35" }}>
                <td style={td}>{MDB_LABELS[r.source]}</td>
                <td style={td}><a href={`/notices/${r.id}`}>{r.title}</a></td>
                <td style={td}>{r.country ?? "-"}</td>
                <td style={td}>{r.ag_subsector ?? "-"}</td>
                <td style={td}>{r.deadline_at?.slice(0, 10) ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p style={{ color: "#9aa3b2", fontSize: 13 }}>{filtered.length}건</p>
    </div>
  );
}

const inputStyle: React.CSSProperties = { background: "#181b22", color: "#e7e9ee", border: "1px solid #272b35", borderRadius: 8, padding: "8px 12px" };
const th: React.CSSProperties = { padding: "8px 10px" };
const td: React.CSSProperties = { padding: "8px 10px" };
