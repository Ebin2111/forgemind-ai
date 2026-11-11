"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import DiagnosisView from "@/components/DiagnosisView";
import Drawer from "@/components/Drawer";
import EmptyState from "@/components/EmptyState";
import EquipmentForm from "@/components/EquipmentForm";
import ImportButton from "@/components/ImportButton";
import Icon from "@/components/Icon";
import StatusPill from "@/components/StatusPill";
import Tabs, { tabId } from "@/components/Tabs";
import { api } from "@/lib/api";
import { errorMessage, formatDate, hours, plural, titleCase } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useFetch } from "@/lib/useFetch";
import { useMediaQuery } from "@/lib/useMediaQuery";
import type { Equipment, TroubleshootResponse, WorkOrder } from "@/types";
import styles from "./equipment.module.css";

const SEARCH_ICON = "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3";
const PLUS_ICON = "M12 5v14M5 12h14";
const BOLT_ICON = "M13 2L4 14h7l-1 8 9-12h-7z";
const STATUS_ORDER = ["operational", "maintenance", "fault", "retired"];
const PRIORITY_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
const COMMON = new Set(["with", "from", "that", "this", "have", "were", "been", "into", "after", "before", "check", "checked", "inspection", "replace", "replaced", "work", "order", "during", "when", "than", "also", "only", "need", "needs"]);

/** Plain-language findings worked out from the equipment's own work orders. Nothing here is estimated or invented. */
function insightsFor(orders: WorkOrder[], fleetDowntime: number): string[] {
  if (orders.length === 0) return [];
  const out: string[] = [];

  const open = orders.filter((o) => o.status !== "closed");
  if (open.length) {
    const top = [...open].sort((a, b) => (PRIORITY_RANK[b.priority] ?? 0) - (PRIORITY_RANK[a.priority] ?? 0))[0];
    out.push(`${plural(open.length, "work order")} still open. Most urgent: "${top.title}" (${top.priority} priority).`);
  } else {
    out.push("No open work orders.");
  }

  const downtime = orders.reduce((s, o) => s + o.downtime_hours, 0);
  if (downtime > 0) {
    const share = fleetDowntime > 0 ? ` That is ${Math.round((downtime / fleetDowntime) * 100)}% of all downtime logged in the plant.` : "";
    out.push(`${hours(downtime)} of downtime logged.${share}`);
  }

  const seen = new Map<string, number>();
  for (const o of orders) {
    const words = new Set(`${o.title} ${o.description}`.toLowerCase().match(/[a-z]{4,}/g) ?? []);
    words.forEach((w) => !COMMON.has(w) && seen.set(w, (seen.get(w) ?? 0) + 1));
  }
  const repeated = [...seen.entries()].filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 3);
  if (repeated.length) out.push(`Recurring in its history: ${repeated.map(([w, n]) => `${w} (${plural(n, "job")})`).join(", ")}.`);

  const lastClosed = orders.filter((o) => o.status === "closed").map((o) => o.created_at).sort().pop();
  if (lastClosed) {
    const days = Math.max(0, Math.round((Date.now() - new Date(`${lastClosed}T00:00:00`).getTime()) / 86_400_000));
    out.push(`Last completed work was ${days === 0 ? "today" : `${plural(days, "day")} ago`} (${formatDate(lastClosed)}).`);
  }
  return out;
}

function Profile({ e, fleetDowntime, isAdmin, onEdit, onDelete }: { e: Equipment; fleetDowntime: number; isAdmin: boolean; onEdit: () => void; onDelete: () => void }) {
  const [tab, setTab] = useState("overview");
  const orders = useFetch(() => api.workOrders({ equipment_id: e.id, limit: 100 }), [e.id]);
  const docs = useFetch(() => (tab === "documents" ? api.passages({ q: `${e.name} ${e.tag}`, limit: 40 }) : Promise.resolve(null)), [e.id, tab]);

  const [symptom, setSymptom] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TroubleshootResponse | null>(null);

  const items = orders.data?.items ?? [];
  const total = orders.data?.total ?? 0;
  const open = items.filter((o) => o.status !== "closed").length;
  const downtime = items.reduce((s, o) => s + o.downtime_hours, 0);
  const last = items.map((o) => o.created_at).sort().pop();
  const insights = useMemo(() => insightsFor(items, fleetDowntime), [items, fleetDowntime]);

  const related = useMemo(() => {
    const groups = new Map<string, { count: number; pages: Set<number>; excerpt: string }>();
    docs.data?.items.forEach((p) => {
      const g = groups.get(p.document) ?? { count: 0, pages: new Set<number>(), excerpt: p.text };
      g.count++;
      g.pages.add(p.page);
      groups.set(p.document, g);
    });
    return [...groups.entries()];
  }, [docs.data]);

  async function diagnose(ev: React.FormEvent) {
    ev.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await api.troubleshoot({ symptom: symptom.trim(), equipment_tag: e.tag, fault_code: code.trim() || null }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "history", label: "Maintenance history", count: total },
    { id: "troubleshoot", label: "Troubleshoot" },
    { id: "documents", label: "Manuals" },
  ];

  return (
    <article className={styles.profile} aria-label={`${e.name} profile`}>
      <header className={styles.hero}>
        <span className={styles.tag}>{e.tag}</span>
        <div className={styles.heroText}>
          <h2>{e.name}</h2>
          <p>{[e.type, e.manufacturer, e.location].filter(Boolean).join(" · ")}</p>
        </div>
        <StatusPill value={e.status} />
      </header>

      <div className={styles.quick}>
        <Link className="button small" href={`/troubleshooting?tag=${encodeURIComponent(e.tag)}`}>Troubleshoot</Link>
        <Link className="button ghost small" href={`/chat?q=${encodeURIComponent(`What are the common faults and routine checks for the ${e.name} (${e.tag})?`)}`}>Ask AI</Link>
        <Link className="button ghost small" href={`/maintenance?equipment=${e.id}`}>Work orders</Link>
        <Link className="button ghost small" href={`/maintenance?new=${e.id}`}>New work order</Link>
        <button type="button" className="ghost small" onClick={onEdit}>{isAdmin ? "Edit" : "Change status"}</button>
        {isAdmin && <button type="button" className="ghost small" onClick={onDelete}>Delete</button>}
      </div>

      <div className={styles.body}>
        <Tabs prefix="eq" label="Equipment details" tabs={tabs} value={tab} onChange={setTab} />

        {tab === "overview" && (
          <div role="tabpanel" aria-labelledby={tabId("eq", "overview")}>
            <div className={styles.tiles}>
              <div className={styles.tile}><div className={styles.n}>{total.toLocaleString()}</div><div className={styles.l}>Work orders</div></div>
              <div className={styles.tile}><div className={styles.n}>{open}</div><div className={styles.l}>Open</div></div>
              <div className={styles.tile}><div className={styles.n}>{hours(downtime)}</div><div className={styles.l}>Downtime logged</div></div>
              <div className={styles.tile}><div className={styles.n} style={{ fontSize: 18 }}>{last ? formatDate(last) : "None"}</div><div className={styles.l}>Latest work order</div></div>
            </div>
            <div className={styles.two}>
              <section>
                <h3 className={styles.sub}>Specifications on record</h3>
                <dl className="kv">
                  <dt>Tag</dt><dd>{e.tag}</dd>
                  <dt>Type</dt><dd>{e.type || "Not recorded"}</dd>
                  <dt>Manufacturer</dt><dd>{e.manufacturer || "Not recorded"}</dd>
                  <dt>Location</dt><dd>{e.location || "Not recorded"}</dd>
                  <dt>Status</dt><dd>{titleCase(e.status)}</dd>
                </dl>
              </section>
              <section>
                <h3 className={styles.sub}>Insights from its history</h3>
                {orders.loading && !orders.data ? <p className="muted"><span className="spinner" /> Reading work orders…</p>
                  : insights.length === 0 ? <p className="muted">No maintenance history yet, so there is nothing to analyse.</p>
                  : <ul className={styles.insights}>{insights.map((t) => <li key={t}><Icon d={BOLT_ICON} size={16} />{t}</li>)}</ul>}
                {total > items.length && <p className="muted" style={{ marginTop: 8 }}>Based on the latest {items.length} of {total} work orders.</p>}
              </section>
            </div>
          </div>
        )}

        {tab === "history" && (
          <div role="tabpanel" aria-labelledby={tabId("eq", "history")}>
            {orders.error && <p className="error">{orders.error}</p>}
            {orders.data && items.length === 0 && <EmptyState icon="M9 4h6v3H9zM7 5H5v16h14V5h-2M9 14l2 2 4-4" title="No maintenance history">Work orders raised for this equipment will appear here.</EmptyState>}
            <ol className={styles.timeline}>
              {items.map((o) => (
                <li key={o.id}>
                  <span className={styles.when}>{formatDate(o.created_at)}</span>
                  <div className={styles.row}><strong>{o.wo_number}</strong><StatusPill value={o.priority} /><StatusPill value={o.status} /></div>
                  <p>{o.title}</p>
                  {o.description && <p className="muted">{o.description}</p>}
                  <p className="muted">{[o.technician && `Technician: ${o.technician}`, o.downtime_hours > 0 && `${hours(o.downtime_hours)} downtime`].filter(Boolean).join(" · ")}</p>
                </li>
              ))}
            </ol>
          </div>
        )}

        {tab === "troubleshoot" && (
          <div role="tabpanel" aria-labelledby={tabId("eq", "troubleshoot")}>
            <form className={styles.ask} onSubmit={diagnose}>
              <label className="field"><span>What is the problem with {e.tag}?</span>
                <textarea rows={3} value={symptom} onChange={(ev) => setSymptom(ev.target.value)} maxLength={1000} placeholder="Describe what you see, hear or measure" required minLength={3} />
              </label>
              <label className="field"><span>Fault code <em className="hint">(optional)</em></span>
                <input type="text" value={code} onChange={(ev) => setCode(ev.target.value)} maxLength={50} placeholder="As shown on the controller" pattern="[A-Za-z0-9][A-Za-z0-9._:/\-]*" title="Letters, numbers and . _ : / - only" />
              </label>
              <div className="btn-row">
                <button type="submit" disabled={busy || symptom.trim().length < 3}>{busy ? "Diagnosing…" : "Diagnose"}</button>
                <Link className="btn-link" href={`/troubleshooting?tag=${encodeURIComponent(e.tag)}`}>Open full troubleshooting</Link>
              </div>
            </form>
            {error && <p className="error">{error}</p>}
            {result && <DiagnosisView result={result} />}
          </div>
        )}

        {tab === "documents" && (
          <div role="tabpanel" aria-labelledby={tabId("eq", "documents")}>
            {docs.loading && !docs.data && <p className="muted"><span className="spinner" /> Searching your documents…</p>}
            {docs.data && related.length === 0 && <EmptyState icon="M6 3h9l5 5v13H6zM14 3v6h6M9 13h8M9 17h8" title="No manuals mention this equipment">Upload its manual in <Link href="/documents">Documents</Link> and it will show up here.</EmptyState>}
            <div className={styles.docs}>
              {related.map(([name, g]) => (
                <div key={name} className={styles.doc}>
                  <strong>{name}</strong>
                  <p className="muted">{plural(g.count, "matching passage")} · page{g.pages.size === 1 ? "" : "s"} {[...g.pages].sort((a, b) => a - b).join(", ")}</p>
                  <p>{g.excerpt.length > 220 ? `${g.excerpt.slice(0, 220).trimEnd()}…` : g.excerpt}</p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </article>
  );
}

function EquipmentView() {
  const params = useSearchParams();
  const wide = useMediaQuery("(min-width: 1101px)");
  const { isAdmin } = useSession();
  const list = useFetch(() => api.equipmentPage({ limit: 500 }), []);
  const summary = useFetch(() => api.analytics(), []);

  const [term, setTerm] = useState("");
  const [status, setStatus] = useState("all");
  const [type, setType] = useState("all");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [form, setForm] = useState<"add" | "edit" | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => { document.title = "Equipment | ForgeMind AI"; }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);

  const all = list.data?.items ?? [];
  const types = useMemo(() => [...new Set(all.map((e) => e.type).filter(Boolean))].sort(), [all]);
  const shown = useMemo(() => {
    const t = term.trim().toLowerCase();
    return all.filter((e) => (status === "all" || e.status === status) && (type === "all" || e.type === type) &&
      (!t || [e.tag, e.name, e.type, e.location, e.manufacturer].some((f) => f.toLowerCase().includes(t))));
  }, [all, term, status, type]);

  // Open the equipment named in ?tag=, otherwise (on wide screens) the first one in the list.
  useEffect(() => {
    if (selectedId !== null || all.length === 0) return;
    const wanted = params.get("tag")?.toLowerCase();
    const match = wanted ? all.find((e) => e.tag.toLowerCase() === wanted) : undefined;
    if (match) { setSelectedId(match.id); setDrawer(!wide); }
    else if (wide) setSelectedId(shown[0]?.id ?? all[0].id);
  }, [all, shown, wide, params, selectedId]);

  const selected = all.find((e) => e.id === selectedId) ?? null;
  const counts = summary.data?.equipment_by_status ?? all.reduce<Record<string, number>>((m, e) => ({ ...m, [e.status]: (m[e.status] ?? 0) + 1 }), {});
  const total = summary.data?.equipment_total ?? all.length;
  const statuses = [...STATUS_ORDER.filter((s) => counts[s]), ...Object.keys(counts).filter((s) => !STATUS_ORDER.includes(s) && counts[s])];
  const operational = counts["operational"] ?? 0;
  const fleetDowntime = summary.data?.downtime_hours_total ?? 0;

  function refresh() { list.reload(); summary.reload(); }

  async function remove(e: Equipment) {
    if (!window.confirm(`Delete ${e.tag} (${e.name}) and all of its work orders? This cannot be undone.`)) return;
    try {
      await api.deleteEquipment(e.id);
      setSelectedId(null);
      setDrawer(false);
      setToast(`${e.tag} deleted.`);
      refresh();
    } catch (err) {
      setToast(errorMessage(err));
    }
  }

  function choose(id: number) {
    setSelectedId(id);
    if (!wide) setDrawer(true);
  }

  return (
    <div className={styles.page}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Equipment</h1>
          <p className="page-sub">Every machine in the registry, with its maintenance history and manuals.</p>
        </div>
        {isAdmin && (
          <div className="btn-row">
            <ImportButton label="Import CSV" columns="tag, name, type, location, manufacturer, status" run={api.importEquipment} onDone={refresh} />
            <button type="button" onClick={() => setForm("add")}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}><Icon d={PLUS_ICON} size={16} />Add equipment</span>
            </button>
          </div>
        )}
      </header>

      {list.error && <div className="alert" role="alert"><p>{list.error}</p><button type="button" onClick={list.reload}>Try again</button></div>}

      {all.length > 0 && (
        <div className={styles.cards}>
          <div className={styles.card}>
            <span className={styles.l}>Operational rate</span>
            <span className={styles.n}>{total ? Math.round((operational / total) * 100) : 0}%</span>
            <span className={styles.meter}><span style={{ width: `${total ? (operational / total) * 100 : 0}%` }} /></span>
          </div>
          <div className={styles.card}><span className={styles.l}>Total equipment</span><span className={styles.n}>{total.toLocaleString()}</span></div>
          {statuses.map((s) => (
            <button key={s} type="button" className={styles.card} style={{ textAlign: "left", color: "inherit", cursor: "pointer" }}
                    onClick={() => setStatus(status === s ? "all" : s)} aria-pressed={status === s}>
              <StatusPill value={s} /><span className={styles.n}>{counts[s]}</span>
            </button>
          ))}
        </div>
      )}

      <div className="toolbar">
        <div className="search grow">
          <Icon d={SEARCH_ICON} size={16} />
          <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search by tag, name, type, location or manufacturer" aria-label="Search equipment" />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
          <option value="all">All statuses</option>
          {statuses.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </select>
        <select value={type} onChange={(e) => setType(e.target.value)} aria-label="Filter by type">
          <option value="all">All types</option>
          {types.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>

      {list.loading && !list.data && <div className="skeleton" style={{ height: 260 }} />}
      {list.data && all.length === 0 && (
        <div className="panel"><EmptyState icon={BOLT_ICON} title="No equipment yet">
          {isAdmin
            ? <>Upload a manual in <Link href="/upload">Upload</Link> and its machine is added here automatically, or use <strong>Add equipment</strong> / <strong>Import CSV</strong> above.</>
            : "An administrator has not added any machines yet."}
        </EmptyState></div>
      )}

      {all.length > 0 && (
        <div className={styles.layout}>
          <div className={styles.list} role="list" aria-label="Equipment directory">
            {shown.length === 0 && <div className="panel"><EmptyState icon={SEARCH_ICON} title="No equipment matches">Try a different search or clear the filters.</EmptyState></div>}
            {shown.map((e) => (
              <button key={e.id} type="button" role="listitem" className={`${styles.item}${e.id === selectedId ? ` ${styles.on}` : ""}`} onClick={() => choose(e.id)} aria-current={e.id === selectedId}>
                <span className={styles.itemTop}><strong>{e.tag}</strong><StatusPill value={e.status} /></span>
                <span>{e.name}</span>
                <span className={styles.itemSub}>{[e.type, e.location].filter(Boolean).join(" · ")}</span>
              </button>
            ))}
            {list.data && list.data.total > all.length && <p className="muted">Showing the first {all.length} of {list.data.total}. Use search to narrow the list.</p>}
          </div>

          {wide && (selected ? <Profile key={selected.id} e={selected} fleetDowntime={fleetDowntime} isAdmin={isAdmin} onEdit={() => setForm("edit")} onDelete={() => remove(selected)} /> : <div className="panel"><EmptyState icon={BOLT_ICON} title="Select equipment">Choose a machine to see its profile.</EmptyState></div>)}
        </div>
      )}

      {!wide && (
        <Drawer open={drawer && !!selected} onClose={() => setDrawer(false)} title={selected?.name ?? ""} subtitle={selected?.tag}>
          {selected && <Profile key={selected.id} e={selected} fleetDowntime={fleetDowntime} isAdmin={isAdmin} onEdit={() => setForm("edit")} onDelete={() => remove(selected)} />}
        </Drawer>
      )}

      <Drawer open={form !== null} onClose={() => setForm(null)} title={form === "edit" ? (isAdmin ? "Edit equipment" : "Change status") : "Add equipment"}
              subtitle={form === "edit" ? selected?.tag : "Every number in the app is worked out from what you enter here."}>
        {form && (
          <EquipmentForm key={form === "edit" ? selected?.id : "new"} existing={form === "edit" ? selected ?? undefined : undefined} statusOnly={!isAdmin} onClose={() => setForm(null)}
                         onDone={(saved) => { setForm(null); setSelectedId(saved.id); setToast(`${saved.tag} saved.`); refresh(); }} />
        )}
      </Drawer>

      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}

export default function EquipmentPage() {
  return <Suspense fallback={null}><EquipmentView /></Suspense>;
}