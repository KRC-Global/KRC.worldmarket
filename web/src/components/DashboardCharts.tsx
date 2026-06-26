import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { supabase } from "../lib/supabase";
import { MDB_LABELS, type MdbSource } from "../types";

// Slack 카테고리 팔레트 — 멀티시리즈 데이터 전용
const SLACK = ["#4a154b", "#36c5f0", "#2eb67d", "#ecb22e", "#e01e5a", "#b07fca", "#1ab9ff"];

const tooltipStyle = {
  background: "#1f2125",
  border: "1px solid #34363b",
  borderRadius: 10,
  color: "#e8e9eb",
  fontSize: 13,
  boxShadow: "0 10px 30px rgb(0 0 0 / .35)",
} as const;

interface ByMdb { source: MdbSource; notice_count: number; open_count: number }
interface BySector { ag_subsector: string; notice_count: number }

export default function DashboardCharts() {
  const [byMdb, setByMdb] = useState<ByMdb[]>([]);
  const [bySector, setBySector] = useState<BySector[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [m, s] = await Promise.all([
        supabase.from("v_stats_by_mdb").select("*"),
        supabase.from("v_stats_by_sector").select("*"),
      ]);
      if (m.error || s.error) { setErr(m.error?.message || s.error?.message || "load error"); setLoading(false); return; }
      setByMdb((m.data ?? []).map((d: any) => ({ ...d, label: MDB_LABELS[d.source as MdbSource] ?? d.source })));
      setBySector(s.data ?? []);
      setLoading(false);
    })();
  }, []);

  return (
    <div className="grid charts-grid" style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr)" }}>
      <style>{`@media (max-width:860px){.charts-grid{grid-template-columns:1fr !important}}`}</style>

      <div className="card pad-lg">
        <h3>MDB별 공고 수</h3>
        <ChartBody loading={loading} err={err} empty={byMdb.length === 0}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={byMdb as any} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2c31" vertical={false} />
              <XAxis dataKey="label" stroke="#6e7178" tick={{ fontSize: 12 }} tickLine={false} axisLine={{ stroke: "#34363b" }} />
              <YAxis stroke="#6e7178" tick={{ fontSize: 12 }} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgb(74 21 75 / .18)" }} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#9a9da3" }} />
              <Bar dataKey="notice_count" fill="#4a154b" name="전체" radius={[5, 5, 0, 0]} />
              <Bar dataKey="open_count" fill="#36c5f0" name="진행중" radius={[5, 5, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartBody>
      </div>

      <div className="card pad-lg">
        <h3>세부 분야별</h3>
        <ChartBody loading={loading} err={err} empty={bySector.length === 0}>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie
                data={bySector as any} dataKey="notice_count" nameKey="ag_subsector"
                innerRadius={52} outerRadius={96} paddingAngle={2} stroke="none"
              >
                {bySector.map((_, i) => <Cell key={i} fill={SLACK[i % SLACK.length]} />)}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#9a9da3" }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartBody>
      </div>
    </div>
  );
}

function ChartBody({ loading, err, empty, children }: {
  loading: boolean; err: string | null; empty: boolean; children: React.ReactNode;
}) {
  if (err) return <Placeholder tone="error">데이터 로드 오류: {err}</Placeholder>;
  if (loading) return <Placeholder>불러오는 중…</Placeholder>;
  if (empty) return <Placeholder>표시할 데이터가 없습니다.</Placeholder>;
  return <>{children}</>;
}

function Placeholder({ children, tone }: { children: React.ReactNode; tone?: "error" }) {
  return (
    <div style={{
      height: 280, display: "grid", placeItems: "center",
      color: tone === "error" ? "#e01e5a" : "#6e7178", fontSize: 14,
      border: "1px dashed #2a2c31", borderRadius: 10,
    }}>
      {children}
    </div>
  );
}
