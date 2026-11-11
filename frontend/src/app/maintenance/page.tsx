"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { ColumnChart, HBars, SegmentBar } from "@/components/charts";
import Drawer from "@/components/Drawer";
import EmptyState from "@/components/EmptyState";
import Icon from "@/components/Icon";
import ImportButton from "@/components/ImportButton";
import StatusPill from "@/components/StatusPill";
import Tabs from "@/components/Tabs";
import { api } from "@/lib/api";
import { errorMessage, formatDate, hours, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useDebounced, useFetch } from "@/lib/useFetch";
import type { Equipment, Priority, WorkOrder, WorkOrderStatus } from "@/types";
import styles from "./maintenance.module.css";

const SEARCH_ICON = "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3";
const PLUS_ICON = "M12 5v14M5 12h14";
const PAGE_SIZE = 15;
const PRIORITIES: Priority[] = ["critical", "high", "medium", "low"]; // the values the backend accepts
const STATUS_COLORS: Record<string, string> = { open: "#e5645f", in_progress: "#d9a62e", closed: "#3fb27a" };
const STATUS_LABELS: Record<string, string> = { open: "Open", in_progress: "In progress", closed: "Closed" };
const monthLabel = (m: string) => {
  const [y, mo] = m.split("-").map(Number);
  return `${new Date(Date.UTC(y, mo - 1, 1)).toLocaleString("en", { month: "short", timeZone: "UTC" })} '${String(y).slice(2)}`;
};

function CreateForm({ equipment, initialEquipment, onDone, onClose }: {
  equipment: Equipment[]; initialEquipment: number | null; onDone: (wo: WorkOrder) => void; onClose: () => void;
}) {
  const [equipmentId, setEquipmentId] = useState<string>(initialEquipment ? String(initialEquipment) : "");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [technician, setTechnician] = useState("");
  const [downtime, setDowntime] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onDone(await api.createWorkOrder({
        equipment_id: Number(equipmentId), title: title.trim(), description: description.trim(),
        priority, technician: technician.trim(), downtime_hours: downtime ? Number(downtime) : 0,
      }));
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <form id="create-wo" className="form-grid" onSubmit={submit}>
      <label className="field"><span>Equipment</span>
        <select value={equipmentId} onChange={(e) => setEquipmentId(e.target.value)} required>
          <option value="" disabled>Choose equipment</option>
          {equipment.map((e) => <option key={e.id} value={e.id}>{e.tag} · {e.name}</option>)}
        </select>
      </label>
      <label className="field"><span>Title</span>
        <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} required minLength={3} maxLength={200} placeholder="What needs to be done?" />
      </label>
      <label className="field"><span>Description <em className="hint">(optional)</em></span>
        <textarea rows={4} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={4000} placeholder="Symptoms, parts, safety notes" />
      </label>
      <div className="form-grid two">
        <label className="field"><span>Priority</span>
          <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
            {PRIORITIES.map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}
          </select>
        </label>
        <label className="field"><span>Assigned technician <em className="hint">(optional)</em></span>
          <input type="text" value={technician} onChange={(e) => setTechnician(e.target.value)} maxLength={100} />
        </label>
      </div>
      <label className="field"><span>Downtime so far, in hours <em className="hint">(optional)</em></span>
        <input type="number" min={0} step="any" value={downtime} onChange={(e) => setDowntime(e.target.value)} />
      </label>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="btn-row">
        <button type="submit" disabled={busy || !equipmentId || title.trim().length < 3}>{busy ? "Creating…" : "Create work order"}</button>
        <button type="button" className="ghost" onClick={onClose} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}

function MaintenanceView() {
  const params = useSearchParams();
  const [tab, setTab] = useState("all");
  const [term, setTerm] = useState("");
  const [priority, setPriority] = useState("all");
  const [equipmentId, setEquipmentId] = useState(params.get("equipment") ?? "all");
  const [offset, setOffset] = useState(0);
  const [openWo, setOpenWo] = useState<WorkOrder | null>(null);
  const [creating, setCreating] = useState(params.get("new") !== null);
  const [toast, setToast] = useState<string | null>(null);
  const q = useDebounced(term, 300);

  const { isAdmin } = useSession();
  const summary = useFetch(() => api.analytics(), []);
  const equipment = useFetch(() => api.equipmentPage({ limit: 500 }), []);
  // Urgent = critical or high priority that is not closed. Counted from the totals of four small queries.
  const urgent = useFetch(async () => {
    const counts = await Promise.all(
      (["open", "in_progress"] as const).flatMap((status) =>
        (["critical", "high"] as const).map((p) => api.workOrders({ status, priority: p, limit: 1 }).then((r) => r.total))),
    );
    return counts.reduce((a, b) => a + b, 0);
  }, []);
  const orders = useFetch(
    () => api.workOrders({
      status: tab === "all" ? undefined : tab, priority: priority === "all" ? undefined : priority,
      equipment_id: equipmentId === "all" ? undefined : Number(equipmentId), q, limit: PAGE_SIZE, offset,
    }),
    [tab, priority, equipmentId, q, offset],
  );

  useEffect(() => { document.title = "Maintenance | ForgeMind AI"; }, []);
  useEffect(() => setOffset(0), [tab, priority, equipmentId, q]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const eq = equipment.data?.items ?? [];
  const tagOf = (id: number) => eq.find((e) => e.id === id);
  const s = summary.data;
  const byStatus = s?.work_orders_by_status ?? {};
  const rows = orders.data?.items ?? [];
  const total = orders.data?.total ?? 0;

  const tabs = useMemo(() => [
    { id: "all", label: "All", count: s?.work_orders_total },
    ...["open", "in_progress", "closed"].map((id) => ({ id, label: STATUS_LABELS[id], count: byStatus[id] ?? 0 })),
  ], [s, byStatus]);

  function refreshAll() { summary.reload(); orders.reload(); urgent.reload(); }

  async function changeStatus(wo: WorkOrder, status: WorkOrderStatus) {
    try {
      const saved = await api.updateWorkOrder(wo.id, { status });
      setOpenWo(saved);
      setToast(`${saved.wo_number} is now ${STATUS_LABELS[saved.status].toLowerCase()}.`);
      refreshAll();
    } catch (err) {
      setToast(errorMessage(err));
    }
  }

  async function removeOrder(wo: WorkOrder) {
    if (!window.confirm(`Delete ${wo.wo_number}? This cannot be undone.`)) return;
    try {
      await api.deleteWorkOrder(wo.id);
      setOpenWo(null);
      setToast(`${wo.wo_number} deleted.`);
      refreshAll();
    } catch (err) {
      setToast(errorMessage(err));
    }
  }

  const filtered = term !== "" || priority !== "all" || equipmentId !== "all" || tab !== "all";

  return (
    <div className={styles.page}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Maintenance</h1>
          <p className="page-sub">Work orders across the plant: what is open, what is urgent and how it trends.</p>
        </div>
        <div className="btn-row">
          {isAdmin && (
            <ImportButton label="Import CSV" columns="equipment_tag, title, priority, status, technician, created_at, downtime_hours, description"
                          run={api.importWorkOrders} onDone={refreshAll} />
          )}
          <button type="button" onClick={() => setCreating(true)} disabled={eq.length === 0} title={eq.length === 0 ? "Add equipment first" : undefined}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><Icon d={PLUS_ICON} size={16} />Create work order</span>
          </button>
        </div>
      </header>

      {summary.error && <div className="alert" role="alert"><p>{summary.error}</p><button type="button" onClick={() => { summary.reload(); orders.reload(); }}>Try again</button></div>}

      {s && (
        <>
          <div className={styles.kpis}>
            <button type="button" className={styles.kpi} onClick={() => setTab("all")}><span className={styles.l}>Total work orders</span><span className={styles.n}>{s.work_orders_total.toLocaleString()}</span><span className={styles.h}>{hours(s.downtime_hours_total)} logged downtime</span></button>
            <button type="button" className={styles.kpi} onClick={() => setTab("closed")} style={{ ["--glow" as string]: "rgba(63,178,122,0.22)" }}><span className={styles.l}>Completed</span><span className={styles.n}>{(byStatus["closed"] ?? 0).toLocaleString()}</span><span className={styles.h}>{s.work_orders_total ? Math.round(((byStatus["closed"] ?? 0) / s.work_orders_total) * 100) : 0}% of all work orders</span></button>
            <button type="button" className={styles.kpi} onClick={() => setTab("in_progress")} style={{ ["--glow" as string]: "rgba(217,166,46,0.22)" }}><span className={styles.l}>In progress</span><span className={styles.n}>{(byStatus["in_progress"] ?? 0).toLocaleString()}</span><span className={styles.h}>being worked on now</span></button>
            <button type="button" className={styles.kpi} onClick={() => setTab("open")} style={{ ["--glow" as string]: "rgba(229,100,95,0.24)" }}><span className={styles.l}>Open</span><span className={styles.n}>{(byStatus["open"] ?? 0).toLocaleString()}</span><span className={styles.h}>{urgent.data !== null && urgent.data !== undefined ? `${urgent.data} urgent (critical or high) not closed` : "waiting to start"}</span></button>
          </div>

          <div className={styles.charts}>
            <section className="panel" aria-label="Work orders per month">
              <h2 className={styles.chartTitle}>Work orders per month</h2>
              <ColumnChart items={s.work_orders_by_month.slice(-12).map((m) => ({ label: monthLabel(m.month), value: m.work_orders }))} empty="No work orders yet." />
            </section>
            <section className="panel" aria-label="Work orders by status">
              <h2 className={styles.chartTitle}>By status</h2>
              <SegmentBar items={["open", "in_progress", "closed"].map((k) => ({ label: STATUS_LABELS[k], value: byStatus[k] ?? 0, color: STATUS_COLORS[k] }))} />
            </section>
            <section className="panel" aria-label="Work orders by priority">
              <h2 className={styles.chartTitle}>By priority</h2>
              <HBars items={PRIORITIES.map((p) => ({ label: titleCase(p), value: s.work_orders_by_priority[p] ?? 0 })).filter((i) => i.value > 0)} empty="No work orders yet." />
            </section>
          </div>
        </>
      )}

      <Tabs prefix="wo" label="Work order status" tabs={tabs} value={tab} onChange={setTab} />

      <div className="toolbar">
        <div className="search grow">
          <Icon d={SEARCH_ICON} size={16} />
          <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search by number, title or description" aria-label="Search work orders" />
        </div>
        <select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Filter by priority">
          <option value="all">All priorities</option>
          {PRIORITIES.map((p) => <option key={p} value={p}>{titleCase(p)}</option>)}
        </select>
        <select value={equipmentId} onChange={(e) => setEquipmentId(e.target.value)} aria-label="Filter by equipment">
          <option value="all">All equipment</option>
          {eq.map((e) => <option key={e.id} value={e.id}>{e.tag} · {e.name}</option>)}
        </select>
        {filtered && <button type="button" className="ghost small" onClick={() => { setTerm(""); setPriority("all"); setEquipmentId("all"); setTab("all"); }}>Clear filters</button>}
      </div>

      {orders.error && <div className="alert" role="alert"><p>{orders.error}</p><button type="button" onClick={orders.reload}>Try again</button></div>}

      <section className="panel" aria-label="Work orders" aria-busy={orders.loading}>
        {orders.data && rows.length === 0 ? (
          <EmptyState icon="M9 4h6v3H9zM7 5H5v16h14V5h-2M9 14l2 2 4-4" title={filtered ? "No work orders match" : "No work orders yet"}>
            {filtered ? "Try different filters." : eq.length === 0
              ? <>Add equipment first: {isAdmin ? <>upload a manual in <Link href="/upload">Upload</Link>, or use <Link href="/equipment">Equipment</Link>.</> : "ask an administrator to add machines."} Then create work orders here.</>
              : (isAdmin ? "Use Create work order, or Import CSV, to start tracking maintenance." : "Use Create work order to start tracking maintenance.") + " The charts above fill in from them."}
          </EmptyState>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th>Work order</th><th>Equipment</th><th>Title</th><th>Priority</th><th>Status</th><th>Technician</th><th>Date</th><th className={styles.num}>Downtime</th></tr></thead>
              <tbody>
                {rows.map((o) => (
                  <tr key={o.id} tabIndex={0} onClick={() => setOpenWo(o)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setOpenWo(o))}>
                    <td><strong>{o.wo_number}</strong></td>
                    <td>{tagOf(o.equipment_id)?.tag ?? `#${o.equipment_id}`}</td>
                    <td className={styles.title}><div title={o.title}>{o.title}</div></td>
                    <td><StatusPill value={o.priority} /></td>
                    <td><StatusPill value={o.status} /></td>
                    <td>{o.technician || <span className="muted">Unassigned</span>}</td>
                    <td>{formatDate(o.created_at)}</td>
                    <td className={styles.num}>{o.downtime_hours > 0 ? hours(o.downtime_hours) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {total > PAGE_SIZE && (
          <div className="pagination">
            <span>{offset + 1} to {Math.min(offset + PAGE_SIZE, total)} of {total.toLocaleString()}</span>
            <span className="btn-row">
              <button type="button" className="ghost small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="ghost small" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
            </span>
          </div>
        )}
      </section>

      <Drawer open={!!openWo} onClose={() => setOpenWo(null)} title={openWo?.wo_number ?? ""} subtitle={openWo?.title}
              footer={openWo && (
                <>
                  <Link className="button ghost small" href={`/equipment?tag=${encodeURIComponent(tagOf(openWo.equipment_id)?.tag ?? "")}`}>Equipment profile</Link>
                  <Link className="button small" href={`/troubleshooting?tag=${encodeURIComponent(tagOf(openWo.equipment_id)?.tag ?? "")}&q=${encodeURIComponent(openWo.title)}`}>Troubleshoot this</Link>
                </>
              )}>
        {openWo && (
          <div className="fade-up">
            <div className={styles.detailTop}><StatusPill value={openWo.status} /><StatusPill value={openWo.priority} /></div>
            <dl className="kv">
              <dt>Equipment</dt><dd>{tagOf(openWo.equipment_id) ? `${tagOf(openWo.equipment_id)!.tag} · ${tagOf(openWo.equipment_id)!.name}` : `#${openWo.equipment_id}`}</dd>
              <dt>Assigned to</dt><dd>{openWo.technician || "Unassigned"}</dd>
              <dt>Raised</dt><dd>{formatDate(openWo.created_at)}</dd>
              <dt>Downtime</dt><dd>{openWo.downtime_hours > 0 ? hours(openWo.downtime_hours) : "None logged"}</dd>
            </dl>
            <h3 className="muted" style={{ margin: "18px 0 6px", fontWeight: 600 }}>Description</h3>
            <p className={styles.desc}>{openWo.description || "No description was entered."}</p>
            <div className="btn-row" style={{ marginTop: 18 }}>
              {openWo.status === "open" && <button type="button" className="small" onClick={() => changeStatus(openWo, "in_progress")}>Start work</button>}
              {openWo.status !== "closed" && <button type="button" className="small" onClick={() => changeStatus(openWo, "closed")}>Mark as closed</button>}
              {openWo.status === "closed" && <button type="button" className="ghost small" onClick={() => changeStatus(openWo, "open")}>Reopen</button>}
              {isAdmin && <button type="button" className="ghost small" onClick={() => removeOrder(openWo)}>Delete</button>}
            </div>
          </div>
        )}
      </Drawer>

      <Drawer open={creating} onClose={() => setCreating(false)} title="Create work order" subtitle="The number, date and status are set automatically.">
        <CreateForm equipment={eq} initialEquipment={Number(params.get("new")) || null} onClose={() => setCreating(false)}
                    onDone={(wo) => { setCreating(false); setToast(`${wo.wo_number} created.`); summary.reload(); orders.reload(); urgent.reload(); }} />
      </Drawer>

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}

export default function MaintenancePage() {
  return <Suspense fallback={null}><MaintenanceView /></Suspense>;
}