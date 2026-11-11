"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ColumnChart, HBars, SegmentBar } from "@/components/charts";
import EmptyState from "@/components/EmptyState";
import Icon from "@/components/Icon";
import StatusPill from "@/components/StatusPill";
import { api } from "@/lib/api";
import { hours, plural, shortName, titleCase } from "@/lib/format";
import { useFetch } from "@/lib/useFetch";
import styles from "./analytics.module.css";

const RANGES = [{ id: "3", label: "3 months" }, { id: "6", label: "6 months" }, { id: "12", label: "12 months" }, { id: "all", label: "All" }];
const EQ_COLORS: Record<string, string> = { operational: "#3fb27a", maintenance: "#d9a62e", fault: "#e5645f", retired: "#7a8aa0" };
const WO_COLORS: Record<string, string> = { open: "#e5645f", in_progress: "#d9a62e", closed: "#3fb27a" };
const PRIORITIES = ["critical", "high", "medium", "low"];
const INFO = "M12 16v-4M12 8h.01M22 12a10 10 0 11-20 0 10 10 0 0120 0z";
const WARN = "M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z";

const monthLabel = (m: string) => {
  const [y, mo] = m.split("-").map(Number);
  return `${new Date(Date.UTC(y, mo - 1, 1)).toLocaleString("en", { month: "short", timeZone: "UTC" })} '${String(y).slice(2)}`;
};
const pct = (a: number, b: number) => (b > 0 ? Math.round((a / b) * 100) : 0);
const ordered = (rec: Record<string, number>, order: string[]) => [
  ...order.filter((k) => k in rec), ...Object.keys(rec).filter((k) => !order.includes(k)),
];

export default function AnalyticsPage() {
  const [range, setRange] = useState("6");
  const summary = useFetch(() => api.analytics(), []);
  const equipment = useFetch(() => api.equipmentPage({ limit: 500 }), []);
  const knowledge = useFetch(() => api.knowledgeStats(), []);
  useEffect(() => { document.title = "Analytics | ForgeMind AI"; }, []);

  const s = summary.data;
  const months = useMemo(() => {
    const all = s?.work_orders_by_month ?? [];
    return range === "all" ? all : all.slice(-Number(range));
  }, [s, range]);

  const insights = useMemo(() => {
    if (!s) return [];
    const out: { tone: "info" | "warn"; title: string; text: string }[] = [];
    const top = s.downtime_by_equipment.filter((e) => e.hours > 0).sort((a, b) => b.hours - a.hours)[0];
    if (top && s.downtime_hours_total > 0) out.push({ tone: "warn", title: `${top.tag} causes the most downtime`, text: `${hours(top.hours)} across ${plural(top.work_orders, "work order")}, ${pct(top.hours, s.downtime_hours_total)}% of all logged downtime.` });
    const busiest = [...s.work_orders_by_month].sort((a, b) => b.work_orders - a.work_orders)[0];
    if (busiest) out.push({ tone: "info", title: `${monthLabel(busiest.month)} was the busiest month`, text: `${plural(busiest.work_orders, "work order")} raised and ${hours(busiest.downtime_hours)} of downtime.` });
    const urgent = (s.work_orders_by_priority["critical"] ?? 0) + (s.work_orders_by_priority["high"] ?? 0);
    if (s.work_orders_total > 0) out.push({ tone: s.work_orders_open > 0 ? "warn" : "info", title: `${pct(s.work_orders_total - s.work_orders_open, s.work_orders_total)}% of work orders are closed`, text: `${plural(s.work_orders_open, "work order")} still open. ${plural(urgent, "work order")} overall are critical or high priority.` });
    if (s.work_orders_total > 0) out.push({ tone: "info", title: "Average downtime per work order", text: `${hours(s.downtime_hours_total / s.work_orders_total)} across ${plural(s.work_orders_total, "work order")}.` });
    return out;
  }, [s]);

  const attention = (equipment.data?.items ?? []).filter((e) => e.status === "fault" || e.status === "maintenance");

  function exportCsv() {
    if (!s) return;
    const rows = [["month", "work_orders", "downtime_hours"], ...s.work_orders_by_month.map((m) => [m.month, m.work_orders, m.downtime_hours])];
    const url = URL.createObjectURL(new Blob([rows.map((r) => r.join(",")).join("\n")], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "work-orders-by-month.csv" });
    a.click();
    URL.revokeObjectURL(url);
  }

  const k = knowledge.data;
  const coverage = k && k.passages > 0 ? pct(k.indexed_vectors, k.passages) : 0;

  return (
    <div className={styles.page}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Analytics</h1>
          <p className="page-sub">Plant health, maintenance workload and knowledge coverage, calculated from your live records.</p>
        </div>
        <button type="button" className="ghost" onClick={exportCsv} disabled={!s || s.work_orders_by_month.length === 0}>Export monthly CSV</button>
      </header>

      {summary.error && <div className="alert" role="alert"><p>{summary.error}</p><button type="button" onClick={summary.reload}>Try again</button></div>}
      {summary.loading && !s && <p className="muted" role="status">Loading analytics…</p>}

      {s && s.equipment_total + s.work_orders_total + s.documents === 0 && (
        <EmptyState icon="M4 20V10M10 20V4M16 20v-7M22 20H2" title="Nothing to analyse yet">
          Add equipment, raise work orders or upload manuals and the charts will fill in by themselves.
        </EmptyState>
      )}

      {s && (
        <>
          <div className={styles.kpis}>
            <div className={styles.kpi}><span className={styles.l}>Equipment</span><span className={styles.n}>{s.equipment_total.toLocaleString()}</span><span className={styles.h}>{plural(s.equipment_by_status["operational"] ?? 0, "unit")} operational</span></div>
            <div className={styles.kpi} style={{ ["--glow" as string]: "rgba(229,100,95,0.22)" }}><span className={styles.l}>Open work orders</span><span className={styles.n}>{s.work_orders_open.toLocaleString()}</span><span className={styles.h}>of {s.work_orders_total.toLocaleString()} in total</span></div>
            <div className={styles.kpi} style={{ ["--glow" as string]: "rgba(217,166,46,0.22)" }}><span className={styles.l}>Logged downtime</span><span className={styles.n}>{hours(s.downtime_hours_total)}</span><span className={styles.h}>all work orders</span></div>
            <div className={styles.kpi} style={{ ["--glow" as string]: "rgba(30,120,220,0.25)" }}><span className={styles.l}>Documents</span><span className={styles.n}>{s.documents.toLocaleString()}</span><span className={styles.h}>{plural(s.pages, "page")} · {plural(s.passages, "passage")}</span></div>
          </div>

          {insights.length > 0 && (
            <div className={styles.insights} aria-label="Insights">
              {insights.map((i) => (
                <div key={i.title} className={`${styles.insight}${i.tone === "warn" ? ` ${styles.warn}` : ""}`}>
                  <span className="ic" style={{ width: 36, height: 36, display: "grid", placeItems: "center", borderRadius: 10, background: i.tone === "warn" ? "#3a2f12" : "#0b3036", color: i.tone === "warn" ? "#e0b13a" : "var(--accent)", flex: "none" }}><Icon d={i.tone === "warn" ? WARN : INFO} /></span>
                  <div><strong>{i.title}</strong><span>{i.text}</span></div>
                </div>
              ))}
            </div>
          )}

          <div className={styles.grid}>
            <section className={`panel ${styles.wide}`} aria-label="Work orders per month">
              <div className={styles.cardHead}>
                <h2>Work orders per month</h2>
                <div className={styles.range} role="group" aria-label="Time range">
                  {RANGES.map((r) => <button key={r.id} type="button" aria-pressed={range === r.id} onClick={() => setRange(r.id)}>{r.label}</button>)}
                </div>
              </div>
              <ColumnChart items={months.map((m) => ({ label: monthLabel(m.month), value: m.work_orders }))} empty="No work orders in this period." />
            </section>

            <section className="panel" aria-label="Downtime per month">
              <div className={styles.cardHead}><h2>Downtime per month (hours)</h2></div>
              <ColumnChart items={months.map((m) => ({ label: monthLabel(m.month), value: Math.round(m.downtime_hours * 10) / 10 }))} empty="No downtime logged in this period." />
            </section>

            <section className="panel" aria-label="Downtime by equipment">
              <div className={styles.cardHead}><h2>Downtime by equipment</h2></div>
              <HBars items={[...s.downtime_by_equipment].sort((a, b) => b.hours - a.hours).filter((e) => e.hours > 0).slice(0, 6).map((e) => ({ label: e.tag, sub: e.name, value: e.hours, display: hours(e.hours) }))} empty="No downtime logged yet." />
            </section>

            <section className="panel" aria-label="Equipment by status">
              <div className={styles.cardHead}><h2>Equipment by status</h2></div>
              <SegmentBar items={ordered(s.equipment_by_status, ["operational", "maintenance", "fault", "retired"]).map((k) => ({ label: titleCase(k), value: s.equipment_by_status[k], color: EQ_COLORS[k] ?? "#7a8aa0" }))} />
            </section>

            <section className="panel" aria-label="Work orders by status">
              <div className={styles.cardHead}><h2>Work orders by status</h2></div>
              <SegmentBar items={ordered(s.work_orders_by_status, ["open", "in_progress", "closed"]).map((k) => ({ label: titleCase(k), value: s.work_orders_by_status[k], color: WO_COLORS[k] ?? "#7a8aa0" }))} />
            </section>

            <section className="panel" aria-label="Work orders by priority">
              <div className={styles.cardHead}><h2>Work orders by priority</h2></div>
              <HBars items={PRIORITIES.map((p) => ({ label: titleCase(p), value: s.work_orders_by_priority[p] ?? 0 })).filter((i) => i.value > 0)} empty="No work orders yet." />
            </section>

            <section className="panel" aria-label="Equipment needing attention">
              <div className={styles.cardHead}><h2>Equipment needing attention</h2><Link href="/equipment" className="muted">All equipment</Link></div>
              {attention.length === 0 ? <p className="muted">Nothing is in fault or maintenance.</p> : (
                <ul className={styles.attention}>
                  {attention.map((e) => (
                    <li key={e.id}><Link href={`/equipment?tag=${encodeURIComponent(e.tag)}`}>{e.tag} <span className="muted">· {e.name}</span></Link><StatusPill value={e.status} /></li>
                  ))}
                </ul>
              )}
            </section>

            <section className="panel" aria-label="Passages per document">
              <div className={styles.cardHead}><h2>Passages per document</h2><Link href="/documents" className="muted">All documents</Link></div>
              <HBars items={s.document_stats.map((d) => ({ label: shortName(d.filename), sub: plural(d.pages, "page"), value: d.passages, display: plural(d.passages, "passage") }))} empty="Upload a manual and its passages are counted here." />
            </section>

            <section className="panel" aria-label="Knowledge coverage">
              <div className={styles.cardHead}><h2>Knowledge coverage</h2><Link href="/knowledge-base" className="muted">Open knowledge base</Link></div>
              {k ? (
                <div className={styles.coverage}>
                  <p className="muted" style={{ margin: 0 }}>{plural(k.documents, "document")} split into {plural(k.passages, "passage")}. {k.semantic_enabled ? `Meaning-based search covers ${coverage}% of passages.` : "Meaning-based search is switched off, so keyword search is used."}</p>
                  {k.semantic_enabled && <div className={styles.meter} role="img" aria-label={`${coverage}% of passages indexed for meaning-based search`}><span style={{ width: `${coverage}%` }} /></div>}
                  {k.documents === 0 && <Link className="button small" href="/upload">Upload the first manual</Link>}
                </div>
              ) : <p className="muted">{knowledge.error ?? "Loading…"}</p>}
            </section>
          </div>
        </>
      )}
    </div>
  );
}