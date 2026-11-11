"use client";

import { useEffect, useState } from "react";

import Link from "next/link";

import { HBars } from "@/components/charts";
import StatCard from "@/components/StatCard";
import StatusPill from "@/components/StatusPill";
import { api } from "@/lib/api";
import { shortName } from "@/lib/format";
import type { AnalyticsSummary, Equipment, Health, MonthlyWorkOrders, WorkOrder } from "@/types";

interface Overview {
  summary: AnalyticsSummary;
  health: Health;
  equipment: Equipment[];
  orders: WorkOrder[];
}

const EQUIPMENT_ORDER = ["operational", "maintenance", "fault", "retired"];
const WORK_ORDER_STATUS_ORDER = ["open", "in_progress", "closed"];
const PRIORITY_ORDER = ["critical", "high", "medium", "low"];
const RECENT_ORDERS = 5;
const MAX_MONTHS = 12;

const BACKEND_HINT =
  "Can't reach the backend. From the project folder run: python -m uvicorn backend.app.main:app --port 8000";

function friendlyError(err: unknown): string {
  if (err instanceof TypeError) return BACKEND_HINT; // fetch() could not connect
  return err instanceof Error ? err.message : "Something went wrong.";
}

/** [key, count] pairs: known keys first in a fixed order, then any others; zero counts left out. */
function ordered(counts: Record<string, number>, order: string[]): Array<[string, number]> {
  const known = order.filter((k) => (counts[k] ?? 0) > 0).map((k): [string, number] => [k, counts[k]]);
  const extra = Object.entries(counts).filter(([k, n]) => !order.includes(k) && n > 0);
  return [...known, ...extra];
}

function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  if (!y || !m) return month;
  const name = new Date(Date.UTC(y, m - 1, 1)).toLocaleString("en", { month: "short", timeZone: "UTC" });
  return `${name} '${String(y).slice(2)}`;
}

const hours = (n: number) => `${n.toLocaleString(undefined, { maximumFractionDigits: 1 })} h`;

/** Count per category with a bar showing its share of the total. The pill names the category. */
function Breakdown({ title, entries }: { title: string; entries: Array<[string, number]> }) {
  const total = entries.reduce((sum, [, n]) => sum + n, 0);
  return (
    <section className="panel" aria-label={title}>
      <h2>{title}</h2>
      {entries.length === 0 ? (
        <p className="muted">Nothing recorded yet.</p>
      ) : (
        <ul className="breakdown">
          {entries.map(([key, n]) => (
            <li key={key}>
              <StatusPill value={key} />
              <span className="bar-track" aria-hidden="true">
                <span className="bar-fill" style={{ width: `${(n / total) * 100}%` }} />
              </span>
              <span className="count">{n}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Ranked horizontal bars: equipment with the most downtime. One hue, value at the bar tip. */
function DowntimeChart({ rows }: { rows: AnalyticsSummary["downtime_by_equipment"] }) {
  const max = Math.max(...rows.map((r) => r.hours), 0);
  return (
    <section className="panel" aria-label="Downtime by equipment">
      <h2>Downtime by equipment</h2>
      {rows.length === 0 || max === 0 ? (
        <p className="muted">No downtime logged.</p>
      ) : (
        <ul className="rank">
          {rows.map((r) => (
            <li key={r.tag} aria-label={`${r.tag} ${r.name}: ${hours(r.hours)} over ${r.work_orders} work orders`}>
              <span className="rank-name">
                <strong>{r.tag}</strong>
                <span className="muted">{r.name}</span>
              </span>
              <span className="rank-track">
                <span className="rank-bar" style={{ ["--ratio" as string]: r.hours / max }} />
                <span className="rank-value">
                  {hours(r.hours)}
                  <span className="muted"> · {r.work_orders} WO</span>
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Work orders raised per month, as columns on one baseline with the value on each cap. */
function MonthlyChart({ months }: { months: MonthlyWorkOrders[] }) {
  const shown = months.slice(-MAX_MONTHS);
  const max = Math.max(...shown.map((m) => m.work_orders), 0);
  return (
    <section className="panel" aria-label="Work orders per month">
      <h2>Work orders per month</h2>
      {shown.length === 0 || max === 0 ? (
        <p className="muted">No work orders yet.</p>
      ) : (
        <ul className="columns">
          {shown.map((m) => (
            <li key={m.month} aria-label={`${monthLabel(m.month)}: ${m.work_orders} work orders`}>
              <span className="col-value">{m.work_orders}</span>
              <span className="col-area">
                <span className="col-bar" style={{ height: `${Math.max((m.work_orders / max) * 100, 2)}%` }} />
              </span>
              <span className="col-label">{monthLabel(m.month)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Loading() {
  return (
    <div aria-busy="true">
      <p className="sr-only" role="status">Loading overview</p>
      <div className="kpis">
        {[0, 1, 2, 3].map((i) => <div className="skeleton tile" key={i} />)}
      </div>
      <div className="panels">
        {[0, 1, 2].map((i) => <div className="skeleton block" key={i} />)}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    Promise.all([api.analytics(), api.health(), api.equipment(), api.maintenance()])
      .then(([summary, health, equipment, orders]) => {
        if (!cancelled) setData({ summary, health, equipment, orders });
      })
      .catch((err) => {
        if (!cancelled) setError(friendlyError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const s = data?.summary;
  const tagOf = (id: number) => data?.equipment.find((e) => e.id === id)?.tag ?? `#${id}`;
  const notOperational = s ? s.equipment_total - (s.equipment_by_status["operational"] ?? 0) : 0;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Overview</h1>
          <p className="page-sub">Plant status, maintenance and knowledge base at a glance.</p>
        </div>
        {data && (
          <ul className="health" aria-label="System status">
            <li><span className={`dot ${data.health.status === "ok" ? "ok" : "warn"}`} />Backend {data.health.status === "ok" ? "online" : "degraded"}</li>
            <li><span className={`dot ${data.health.semantic_search ? "ok" : "neutral"}`} />{data.health.semantic_search ? "Semantic search" : "Keyword search"}</li>
            <li><span className={`dot ${data.health.gemini_configured ? "ok" : "neutral"}`} />Gemini {data.health.gemini_configured ? "on" : "off"}</li>
          </ul>
        )}
      </header>

      {error && (
        <div className="alert" role="alert">
          <p>{error}</p>
          <button type="button" onClick={() => setAttempt((n) => n + 1)}>Try again</button>
        </div>
      )}

      {!data && !error && <Loading />}

      {data && s && (
        <>
          <div className="kpis">
            <StatCard label="Equipment registered" value={String(s.equipment_total)}
                      hint={notOperational ? `${notOperational} not fully operational` : "All operational"} />
            <StatCard label="Open work orders" value={String(s.work_orders_open)} hint={`of ${s.work_orders_total} total`} />
            <StatCard label="Logged downtime" value={hours(s.downtime_hours_total)} hint="across all work orders" />
            <StatCard label="Knowledge base" value={`${s.documents} ${s.documents === 1 ? "document" : "documents"}`}
                      hint={`${s.pages} pages · ${s.passages} searchable passages`} />
          </div>

          {s.documents === 0 && s.equipment_total === 0 && s.work_orders_total === 0 && (
            <div className="notice">
              <strong>Nothing here yet.</strong> Every number and chart on this page is worked out from your own data.{" "}
              <Link href="/upload">Upload a PDF manual</Link> to fill the knowledge base and register its machine, then add{" "}
              <Link href="/maintenance">work orders</Link> (or import a CSV) to see maintenance and downtime.
            </div>
          )}
          {s.documents === 0 && (s.equipment_total > 0 || s.work_orders_total > 0) && (
            <div className="notice">
              No manuals are indexed yet, so answers cannot cite documents. <Link href="/upload">Upload a PDF manual or SOP</Link>.
            </div>
          )}
          {s.documents > 0 && s.work_orders_total === 0 && (
            <div className="notice">
              Maintenance charts stay empty until work orders exist. <Link href="/maintenance">Create or import work orders</Link>.
            </div>
          )}

          <div className="panels three">
            <Breakdown title="Equipment by status" entries={ordered(s.equipment_by_status, EQUIPMENT_ORDER)} />
            <Breakdown title="Work orders by status" entries={ordered(s.work_orders_by_status, WORK_ORDER_STATUS_ORDER)} />
            <Breakdown title="Work orders by priority" entries={ordered(s.work_orders_by_priority, PRIORITY_ORDER)} />
          </div>

          <div className="panels two">
            <DowntimeChart rows={s.downtime_by_equipment} />
            <MonthlyChart months={s.work_orders_by_month} />
          </div>

          <section className="panel" aria-label="Uploaded documents">
            <h2>Knowledge base by document</h2>
            <HBars
              items={s.document_stats.map((d) => ({ label: shortName(d.filename), sub: `${d.pages} ${d.pages === 1 ? "page" : "pages"}`, value: d.passages, display: `${d.passages} passages` }))}
              empty="No documents uploaded yet."
            />
          </section>

          <section className="panel" aria-label="Recent work orders">
            <h2>Recent work orders</h2>
            {data.orders.length === 0 ? (
              <p className="muted">No work orders yet.</p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr><th>WO</th><th>Equipment</th><th>Title</th><th>Priority</th><th>Status</th><th>Date</th></tr>
                  </thead>
                  <tbody>
                    {data.orders.slice(0, RECENT_ORDERS).map((o) => (
                      <tr key={o.id}>
                        <td>{o.wo_number}</td>
                        <td>{tagOf(o.equipment_id)}</td>
                        <td>{o.title}</td>
                        <td><StatusPill value={o.priority} /></td>
                        <td><StatusPill value={o.status} /></td>
                        <td>{o.created_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}