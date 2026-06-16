import { useEffect, useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { supabase } from "../lib/supabase";
import { MDB_LABELS, type MdbSource } from "../types";

const COLORS = ["#4ade80", "#60a5fa", "#f59e0b", "#f472b6", "#a78bfa", "#34d399", "#fb7185"];

interface ByMdb { source: MdbSource; notice_count: number; open_count: number }
interface BySector { ag_subsector: string; notice_count: number }

export default function DashboardCharts() {
  const [byMdb, setByMdb] = useState<ByMdb[]>([]);
  const [bySector, setBySector] = useState<BySector[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const [m, s] = await Promise.all([
        supabase.from("v_stats_by_mdb").select("*"),
        supabase.from("v_stats_by_sector").select("*"),
      ]);
      if (m.error || s.error) { setErr(m.error?.message || s.error?.message || "load error"); return; }
      setByMdb((m.data ?? []).map((d: any) => ({ ...d, label: MDB_LABELS[d.source as MdbSource] ?? d.source })));
      setBySector(s.data ?? []);
    })();
  }, []);

  if (err) return <div className="card">데이터 로드 오류: {err}</div>;

  return (
    <div className="grid" style={{ gridTemplateColumns: "2fr 1fr" }}>
      <div className="card">
        <h3>MDB별 공고 수</h3>
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={byMdb as any}>
            <CartesianGrid strokeDasharray="3 3" stroke="#272b35" />
            <XAxis dataKey="label" stroke="#9aa3b2" />
            <YAxis stroke="#9aa3b2" />
            <Tooltip contentStyle={{ background: "#181b22", border: "1px solid #272b35" }} />
            <Bar dataKey="notice_count" fill="#4ade80" name="전체" />
            <Bar dataKey="open_count" fill="#60a5fa" name="진행중" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="card">
        <h3>세부 분야별</h3>
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie data={bySector as any} dataKey="notice_count" nameKey="ag_subsector" outerRadius={100} label>
              {bySector.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
            </Pie>
            <Tooltip contentStyle={{ background: "#181b22", border: "1px solid #272b35" }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
