"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

import DiagnosisView from "@/components/DiagnosisView";
import EmptyState from "@/components/EmptyState";
import Orb from "@/components/Orb";
import StatusPill from "@/components/StatusPill";
import { api } from "@/lib/api";
import { errorMessage, formatDate, hours } from "@/lib/format";
import { useFetch } from "@/lib/useFetch";
import type { TroubleshootResponse } from "@/types";
import styles from "./troubleshooting.module.css";

// Looks like a controller or alarm code: 1-3 letters, optional separator, 2-5 digits (E-204, F0003, ERR12).
const CODE_RE = /\b[A-Za-z]{1,3}[-_]?\d{2,5}\b/g;

function TroubleshootingView() {
  const params = useSearchParams();
  const [tag, setTag] = useState(params.get("tag") ?? "");
  const [code, setCode] = useState("");
  const [symptom, setSymptom] = useState(params.get("q") ?? "");
  const [history, setHistory] = useState(true);
  const [log, setLog] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TroubleshootResponse | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const equipment = useFetch(() => api.equipmentPage({ limit: 500 }), []);
  const eq = equipment.data?.items ?? [];
  useEffect(() => { document.title = "Troubleshooting | ForgeMind AI"; }, []);

  // Tags and codes found in pasted log text. Registry tags are matched against the real equipment list.
  const found = useMemo(() => {
    const tags = new Set(eq.map((e) => e.tag.toUpperCase()));
    const hitsTags: string[] = [];
    const hitsCodes: string[] = [];
    for (const m of log.match(CODE_RE) ?? []) {
      const up = m.toUpperCase();
      if (tags.has(up)) { if (!hitsTags.includes(up)) hitsTags.push(up); }
      else if (!hitsCodes.includes(m)) hitsCodes.push(m);
    }
    for (const t of tags) if (!hitsTags.includes(t) && log.toUpperCase().includes(t)) hitsTags.push(t);
    return { tags: hitsTags.slice(0, 8), codes: hitsCodes.slice(0, 12) };
  }, [log, eq]);

  const selected = eq.find((e) => e.tag.toLowerCase() === tag.toLowerCase());

  async function run(e?: React.FormEvent) {
    e?.preventDefault();
    if (busy || symptom.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.troubleshoot({
        symptom: symptom.trim(), equipment_tag: tag || null, fault_code: code.trim() || null, include_history: history,
      });
      setResult(r);
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const h = result?.history;
  const eqInfo = result?.equipment ?? selected ?? null;

  return (
    <div className={styles.page}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Troubleshooting assistant</h1>
          <p className="page-sub">Describe the fault. The answer comes from your uploaded manuals and this machine&apos;s own work-order history.</p>
        </div>
      </header>

      <div className={styles.layout}>
        <div className={styles.side}>
          <form className="panel" onSubmit={run}>
            <div className={styles.hero}>
              <Orb size={44} thinking={busy} />
              <div><h2>Diagnose a fault</h2><p>{busy ? "Reading manuals and history…" : "Equipment and code are optional."}</p></div>
            </div>
            <div className="form-grid">
              <label className="field"><span>Equipment <em className="hint">(optional)</em></span>
                <select value={tag} onChange={(e) => setTag(e.target.value)} disabled={equipment.loading && eq.length === 0}>
                  <option value="">Not sure / any equipment</option>
                  {eq.map((e) => <option key={e.id} value={e.tag}>{e.tag} · {e.name}</option>)}
                  {tag && !selected && eq.length > 0 && <option value={tag}>{tag}</option>}
                </select>
              </label>
              <label className="field"><span>Fault code <em className="hint">(optional)</em></span>
                <input type="text" value={code} onChange={(e) => setCode(e.target.value)} maxLength={50} pattern="[A-Za-z0-9][A-Za-z0-9._:\/\-]*" title="Letters, digits and . _ : / -" placeholder="As shown on the controller" />
              </label>
              <label className="field"><span>What is happening?</span>
                <textarea rows={5} value={symptom} onChange={(e) => setSymptom(e.target.value)} required minLength={3} maxLength={1000} placeholder="Describe the symptoms in plain words: noises, alarms, when it started" />
              </label>
              <label className="check"><input type="checkbox" checked={history} onChange={(e) => setHistory(e.target.checked)} /> Use this machine&apos;s earlier work orders</label>
              {error && <p className="error" role="alert">{error}</p>}
              <button type="submit" disabled={busy || symptom.trim().length < 3}>{busy ? "Diagnosing…" : "Diagnose"}</button>
            </div>
          </form>

          <section className={`panel ${styles.tool}`} aria-label="Error log analyzer">
            <h2 style={{ margin: "0 0 4px", fontSize: 15 }}>Error log analyzer</h2>
            <p className="muted" style={{ margin: "0 0 10px", fontSize: 13 }}>Paste log lines. Equipment tags and fault codes are picked out so you can use them with one click.</p>
            <textarea rows={5} value={log} onChange={(e) => setLog(e.target.value)} placeholder="Paste error log text here" aria-label="Error log text" maxLength={20000} />
            {log.trim() && (
              found.tags.length + found.codes.length === 0
                ? <p className={styles.note}>No equipment tags or fault codes recognised in this text.</p>
                : (
                  <div className={styles.found}>
                    {found.tags.map((t) => <button key={t} type="button" className="chip" onClick={() => setTag(eq.find((e) => e.tag.toUpperCase() === t)?.tag ?? t)} title="Use as equipment">{t}</button>)}
                    {found.codes.map((c) => <button key={c} type="button" className="chip" onClick={() => setCode(c)} title="Use as fault code">{c}</button>)}
                  </div>
                )
            )}
            {log.trim() && <button type="button" className="ghost small" style={{ marginTop: 10 }} onClick={() => setSymptom((s) => (s ? s + "\n" : "") + log.trim().split(/\r?\n/).slice(0, 5).join("\n").slice(0, 600))}>Add first lines to symptom</button>}
            <p className={styles.note}>Live sensor readings (temperature, pressure, flow) are not connected to this system, so they cannot be analysed here.</p>
          </section>
        </div>

        <div ref={resultRef}>
          {busy && (
            <div className={`panel ${styles.idle}`} role="status"><Orb size={72} thinking /><p>Searching manuals and past work orders for a likely cause…</p></div>
          )}

          {!busy && !result && (
            <div className={`panel ${styles.idle}`}>
              <Orb size={72} />
              <p>{eq.length === 0 && !equipment.loading ? "No equipment is registered yet. You can still describe a fault and search the uploaded manuals." : "Your diagnosis will appear here with causes, checks, corrective actions and the manuals they came from."}</p>
            </div>
          )}

          {!busy && result && (
            <div className="fade-up">
              {eqInfo && (
                <section className="panel" style={{ marginBottom: 16 }} aria-label="Equipment health">
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                    <div><strong>{eqInfo.tag}</strong> · {eqInfo.name}<div className="muted" style={{ fontSize: 13 }}>{eqInfo.type} · {eqInfo.location}</div></div>
                    <StatusPill value={eqInfo.status} />
                  </div>
                  {h && (
                    <div className={styles.health}>
                      <div><b>{h.work_orders_total.toLocaleString()}</b><span>work orders on record</span></div>
                      <div className={h.work_orders_open > 0 ? styles.warn : ""}><b>{h.work_orders_open.toLocaleString()}</b><span>not yet closed</span></div>
                      <div><b>{hours(h.downtime_hours_total)}</b><span>total downtime</span></div>
                      <div><b>{h.last_work_order_date ? formatDate(h.last_work_order_date) : "–"}</b><span>last work order</span></div>
                    </div>
                  )}
                  <div className="btn-row" style={{ marginTop: 12 }}>
                    <Link className="button ghost small" href={`/equipment?tag=${encodeURIComponent(eqInfo.tag)}`}>Equipment profile</Link>
                    <Link className="button small" href={`/maintenance?new=${eqInfo.id}`}>Create work order</Link>
                  </div>
                </section>
              )}
              <DiagnosisView result={result} />
            </div>
          )}
          {!busy && !result && error && <EmptyState icon="M12 9v4M12 17h.01" title="Diagnosis failed">{error}</EmptyState>}
        </div>
      </div>
    </div>
  );
}

export default function TroubleshootingPage() {
  return <Suspense fallback={null}><TroubleshootingView /></Suspense>;
}