"use client";

import Link from "next/link";
import { Fragment, useEffect, useMemo, useState } from "react";

import EmptyState from "@/components/EmptyState";
import Icon from "@/components/Icon";
import { api } from "@/lib/api";
import { plural, stripExt } from "@/lib/format";
import { useDebounced, useFetch } from "@/lib/useFetch";
import type { Passage } from "@/types";
import styles from "./knowledge.module.css";

const SEARCH_ICON = "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3";
const PAGE_SIZE = 10;
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Wraps matches of the search words in <mark>. Builds React elements, never raw HTML. */
function Highlight({ text, query }: { text: string; query: string }) {
  const words = Array.from(new Set(query.toLowerCase().split(/\s+/).filter((w) => w.length > 1)));
  if (words.length === 0) return <>{text}</>;
  const re = new RegExp(`(${words.map(escapeRe).join("|")})`, "gi");
  return <>{text.split(re).map((part, i) => (i % 2 === 1 ? <mark key={i} className={styles.mark}>{part}</mark> : <Fragment key={i}>{part}</Fragment>))}</>;
}

export default function KnowledgeBasePage() {
  const [term, setTerm] = useState("");
  const [doc, setDoc] = useState("");
  const [offset, setOffset] = useState(0);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);
  const q = useDebounced(term.trim(), 300);

  const stats = useFetch(() => api.knowledgeStats(), []);
  const docs = useFetch(() => api.documents(), []);
  const passages = useFetch(() => api.passages({ document: doc || undefined, q: q || undefined, limit: PAGE_SIZE, offset }), [doc, q, offset]);

  useEffect(() => { document.title = "Knowledge Base | ForgeMind AI"; }, []);
  useEffect(() => setOffset(0), [doc, q]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  const list = useMemo(() => (docs.data ?? []).slice().sort((a, b) => a.filename.localeCompare(b.filename)), [docs.data]);
  const k = stats.data;
  const rows = passages.data?.items ?? [];
  const total = passages.data?.total ?? 0;
  const key = (p: Passage) => `${p.document}#${p.chunk_index}`;
  const coverage = k && k.passages > 0 ? Math.round((k.indexed_vectors / k.passages) * 100) : 0;

  async function copy(p: Passage) {
    try {
      await navigator.clipboard.writeText(`${p.text}\n\n(${p.document}, page ${p.page})`);
      setToast("Passage copied with its source.");
    } catch {
      setToast("Copy is not available in this browser.");
    }
  }

  return (
    <div className={styles.page}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Knowledge base</h1>
          <p className="page-sub">Everything the assistant can quote. Search the exact passages behind its answers.</p>
        </div>
        <Link className="button" href="/upload">Add documents</Link>
      </header>

      {(stats.error || passages.error) && <div className="alert" role="alert"><p>{stats.error ?? passages.error}</p><button type="button" onClick={() => { stats.reload(); passages.reload(); }}>Try again</button></div>}

      {k && (
        <div className={styles.kpis}>
          <div className={styles.kpi}><span className={styles.l}>Documents</span><span className={styles.n}>{k.documents.toLocaleString()}</span><span className={styles.h}>{plural(k.pages, "page")}</span></div>
          <div className={styles.kpi} style={{ ["--glow" as string]: "rgba(30,120,220,0.25)" }}><span className={styles.l}>Passages</span><span className={styles.n}>{k.passages.toLocaleString()}</span><span className={styles.h}>searchable sections</span></div>
          <div className={styles.kpi} style={{ ["--glow" as string]: k.semantic_enabled ? "rgba(63,178,122,0.25)" : "rgba(217,166,46,0.25)" }}>
            <span className={styles.l}>Search mode</span><span className={styles.n} style={{ fontSize: 22, paddingTop: 6 }}>{k.semantic_enabled ? "Hybrid" : "Keyword"}</span>
            <span className={styles.h}>{k.semantic_enabled ? `${coverage}% of passages embedded` : "Meaning-based search is off"}</span>
          </div>
          {k.semantic_enabled && <div className={styles.kpi}><span className={styles.l}>Embedding model</span><span className={styles.n} style={{ fontSize: 16, paddingTop: 10, overflowWrap: "anywhere" }}>{k.embedding_model}</span><span className={styles.h}>{k.indexed_vectors.toLocaleString()} vectors</span></div>}
        </div>
      )}

      {k && k.documents === 0 ? (
        <EmptyState icon="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" title="The knowledge base is empty">
          Upload a manual and its passages will appear here, ready to search.
        </EmptyState>
      ) : (
        <div className={styles.layout}>
          <aside className="panel" aria-label="Documents">
            <h2 style={{ margin: "0 0 10px", fontSize: 15 }}>Documents</h2>
            <ul className={styles.docs}>
              <li><button type="button" aria-pressed={doc === ""} onClick={() => setDoc("")}><span className={styles.nm}>All documents</span><span className={styles.ct}>{k?.passages.toLocaleString() ?? ""}</span></button></li>
              {list.map((d) => (
                <li key={d.id}><button type="button" aria-pressed={doc === d.filename} onClick={() => setDoc(d.filename)} title={d.filename}><span className={styles.nm}>{stripExt(d.filename)}</span><span className={styles.ct}>{d.chunks.toLocaleString()}</span></button></li>
              ))}
            </ul>
          </aside>

          <div>
            <div className="toolbar">
              <div className="search grow">
                <Icon d={SEARCH_ICON} size={16} />
                <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search passages, e.g. bearing temperature or fault code" aria-label="Search passages" />
              </div>
              {(term || doc) && <button type="button" className="ghost small" onClick={() => { setTerm(""); setDoc(""); }}>Clear</button>}
            </div>

            <section className="panel" aria-label="Passages" aria-busy={passages.loading}>
              {passages.data && rows.length === 0 ? (
                <EmptyState icon={SEARCH_ICON} title="No passages found">{q ? "Try fewer or different words." : "This document has no indexed passages."}</EmptyState>
              ) : (
                <div className={styles.passages}>
                  <p className="muted" style={{ margin: 0 }}>{q ? `${plural(total, "passage")} match, best first.` : `${plural(total, "passage")}.`}</p>
                  {rows.map((p) => {
                    const open = expanded.has(key(p));
                    const max = Math.max(...rows.map((r) => r.score ?? 0), 0);
                    return (
                      <article key={key(p)} className={styles.passage}>
                        <div className={styles.pTop}>
                          <span className={styles.pTitle}>{p.document} <span>· page {p.page}</span></span>
                          {p.score !== null && max > 0 && <span className={styles.score} title="Relative match strength"><span style={{ width: `${Math.max(8, (p.score / max) * 100)}%` }} /></span>}
                        </div>
                        <p className={`${styles.pText}${open ? "" : ` ${styles.clamp}`}`}><Highlight text={p.text} query={q} /></p>
                        <div className={styles.pActions}>
                          {p.text.length > 280 && <button type="button" className="ghost small" onClick={() => setExpanded((s) => { const n = new Set(s); n.has(key(p)) ? n.delete(key(p)) : n.add(key(p)); return n; })}>{open ? "Show less" : "Show more"}</button>}
                          <button type="button" className="ghost small" onClick={() => copy(p)}>Copy</button>
                          <Link className="button ghost small" href={`/chat?q=${encodeURIComponent(`Explain: ${p.text.slice(0, 150)}`)}`}>Ask about this</Link>
                        </div>
                      </article>
                    );
                  })}
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
          </div>
        </div>
      )}
      {toast && <div className="toast" role="status">{toast}</div>}
    </div>
  );
}