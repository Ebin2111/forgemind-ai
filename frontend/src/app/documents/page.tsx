"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import AnswerText from "@/components/AnswerText";
import Drawer from "@/components/Drawer";
import EmptyState from "@/components/EmptyState";
import Icon from "@/components/Icon";
import Tabs, { tabId } from "@/components/Tabs";
import { api } from "@/lib/api";
import { errorMessage, fileExt, formatDate, plural } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useDebounced, useFetch } from "@/lib/useFetch";
import type { DocumentInfo, DocumentSummary } from "@/types";
import styles from "./documents.module.css";

const UPLOAD_ICON = "M12 16V4M7 9l5-5 5 5M4 20h16";
const FILE_ICON = "M6 3h9l5 5v13H6zM14 3v6h6M9 13h8M9 17h8";
const SEARCH_ICON = "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.3-4.3";
const PASSAGES_PER_PAGE = 8;

type Sort = "newest" | "oldest" | "name" | "pages";
const SORTS: Array<{ id: Sort; label: string }> = [
  { id: "newest", label: "Newest first" },
  { id: "oldest", label: "Oldest first" },
  { id: "name", label: "Name A to Z" },
  { id: "pages", label: "Most pages" },
];

function sortDocs(docs: DocumentInfo[], sort: Sort): DocumentInfo[] {
  const copy = [...docs];
  if (sort === "oldest") return copy.sort((a, b) => a.uploaded_at.localeCompare(b.uploaded_at));
  if (sort === "name") return copy.sort((a, b) => a.filename.localeCompare(b.filename));
  if (sort === "pages") return copy.sort((a, b) => b.pages - a.pages);
  return copy.sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at));
}

/** Wrap matches of `term` in <mark>, without building HTML strings. */
function highlight(text: string, term: string) {
  const t = term.trim();
  if (t.length < 2) return text;
  const escaped = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return text.split(new RegExp(`(${escaped})`, "ig")).map((part, i) =>
    part.toLowerCase() === t.toLowerCase() ? <mark key={i}>{part}</mark> : part,
  );
}

function Preview({ doc }: { doc: DocumentInfo }) {
  const [tab, setTab] = useState("summary");
  const [summary, setSummary] = useState<DocumentSummary | null>(null);
  const [summarizing, setSummarizing] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [term, setTerm] = useState("");
  const [offset, setOffset] = useState(0);
  const q = useDebounced(term, 300);

  const passages = useFetch(
    () => api.passages({ document: doc.filename, q, limit: PASSAGES_PER_PAGE, offset }),
    [doc.filename, q, offset],
  );
  useEffect(() => setOffset(0), [q]);

  async function summarize() {
    setSummarizing(true);
    setSummaryError(null);
    try {
      setSummary(await api.summarizeDocument(doc.id));
    } catch (err) {
      setSummaryError(errorMessage(err));
    } finally {
      setSummarizing(false);
    }
  }

  const total = passages.data?.total ?? 0;
  return (
    <>
      <Tabs prefix="doc" label="Document views" value={tab} onChange={setTab}
            tabs={[{ id: "summary", label: "AI summary" }, { id: "passages", label: "Extracted text", count: doc.chunks }]} />

      {tab === "summary" && (
        <div role="tabpanel" aria-labelledby={tabId("doc", "summary")}>
          {summary ? (
            <div className="fade-up">
              <AnswerText text={summary.answer} />
              <p className="muted" style={{ marginTop: 14 }}>
                {summary.generated_by === "extractive"
                  ? "The AI model is off, so this shows excerpts from the document instead of a written summary."
                  : `Written by ${summary.generated_by} from ${plural(summary.passages_used, "passage")} spread across the document.`}
              </p>
              <button type="button" className="ghost small" style={{ marginTop: 10 }} onClick={summarize} disabled={summarizing}>
                {summarizing ? "Working…" : "Generate again"}
              </button>
            </div>
          ) : summarizing ? (
            <div className={styles.stack} aria-busy="true">
              <p className="muted"><span className="spinner" /> Reading the document…</p>
              {[100, 92, 96, 70].map((w) => <div key={w} className={`skeleton ${styles.skeletonLine}`} style={{ width: `${w}%` }} />)}
            </div>
          ) : (
            <div className={styles.summaryCta}>
              <p>Get the purpose, equipment and key procedures of this document in a few lines, with citations to its pages.</p>
              <button type="button" onClick={summarize}>Generate AI summary</button>
              {summaryError && <p className="error">{summaryError}</p>}
            </div>
          )}
        </div>
      )}

      {tab === "passages" && (
        <div role="tabpanel" aria-labelledby={tabId("doc", "passages")}>
          <div className="search" style={{ marginBottom: 12 }}>
            <Icon d={SEARCH_ICON} size={16} />
            <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search inside this document" aria-label="Search inside this document" />
          </div>
          {passages.error && <p className="error">{passages.error}</p>}
          {passages.data && passages.data.items.length === 0 && <p className="muted">{q ? "No passages match your search." : "No indexed text."}</p>}
          <div className={styles.stack}>
            {passages.data?.items.map((p) => (
              <article key={`${p.page}-${p.chunk_index}`} className={styles.passage}>
                <header><span>Page {p.page}</span>{p.score !== null && <span>Match</span>}</header>
                <p>{highlight(p.text, q)}</p>
              </article>
            ))}
          </div>
          {total > PASSAGES_PER_PAGE && (
            <div className="pagination">
              <span>{offset + 1} to {Math.min(offset + PASSAGES_PER_PAGE, total)} of {total}</span>
              <span className="btn-row">
                <button type="button" className="ghost small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PASSAGES_PER_PAGE))}>Previous</button>
                <button type="button" className="ghost small" disabled={offset + PASSAGES_PER_PAGE >= total} onClick={() => setOffset(offset + PASSAGES_PER_PAGE)}>Next</button>
              </span>
            </div>
          )}
        </div>
      )}
    </>
  );
}

export default function DocumentsPage() {
  const { isAdmin } = useSession();
  const docs = useFetch(() => api.documents(), []);
  const stats = useFetch(() => api.knowledgeStats(), []);

  const [term, setTerm] = useState("");
  const [type, setType] = useState("all");
  const [sort, setSort] = useState<Sort>("newest");
  const [over, setOver] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [toast, setToast] = useState<{ text: string; bad?: boolean } | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => { document.title = "Documents | ForgeMind AI"; }, []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(t);
  }, [toast]);
  useEffect(() => {
    if (confirmId === null) return;
    const t = setTimeout(() => setConfirmId(null), 4000);
    return () => clearTimeout(t);
  }, [confirmId]);

  const refresh = useCallback(() => { docs.reload(); stats.reload(); }, [docs, stats]);

  async function upload(files: FileList | File[]) {
    const list = Array.from(files);
    if (list.length === 0) return;
    let added = 0;
    for (const [i, file] of list.entries()) {
      setUploading(list.length > 1 ? `${file.name} (${i + 1} of ${list.length})` : file.name);
      try {
        const d = await api.upload(file);
        added++;
        setToast({ text: `${d.filename} added: ${plural(d.pages, "page")}, ${plural(d.chunks, "searchable passage")}.` });
      } catch (err) {
        setToast({ text: `${file.name}: ${errorMessage(err)}`, bad: true });
      }
    }
    setUploading(null);
    if (added) refresh();
    if (fileInput.current) fileInput.current.value = "";
  }

  async function reindex(d: DocumentInfo) {
    setBusyId(d.id);
    try {
      const r = await api.reindexDocument(d.id);
      setToast({ text: `${r.filename} re-indexed: ${plural(r.chunks, "passage")}.` });
      refresh();
    } catch (err) {
      setToast({ text: errorMessage(err), bad: true });
    } finally {
      setBusyId(null);
    }
  }

  async function remove(d: DocumentInfo) {
    if (confirmId !== d.id) return setConfirmId(d.id);
    setBusyId(d.id);
    setConfirmId(null);
    try {
      await api.deleteDocument(d.id);
      setToast({ text: `${d.filename} removed from the knowledge base.` });
      if (openId === d.id) setOpenId(null);
      refresh();
    } catch (err) {
      setToast({ text: errorMessage(err), bad: true });
    } finally {
      setBusyId(null);
    }
  }

  const all = docs.data ?? [];
  const types = useMemo(() => {
    const counts = new Map<string, number>();
    all.forEach((d) => counts.set(fileExt(d.filename), (counts.get(fileExt(d.filename)) ?? 0) + 1));
    return Array.from(counts.entries()).sort();
  }, [all]);

  const shown = useMemo(() => {
    const t = term.trim().toLowerCase();
    return sortDocs(all.filter((d) => (type === "all" || fileExt(d.filename) === type) && (!t || d.filename.toLowerCase().includes(t))), sort);
  }, [all, term, type, sort]);

  const open = all.find((d) => d.id === openId) ?? null;

  function actions(d: DocumentInfo) {
    const busy = busyId === d.id;
    return (
      <>
        <a className="button ghost small" href={api.downloadUrl(d.id)}>Download</a>
        {isAdmin && <button type="button" className="ghost small" onClick={() => reindex(d)} disabled={busy}>{busy ? "Working…" : "Re-index"}</button>}
        {isAdmin && <button type="button" className="danger small" onClick={() => remove(d)} disabled={busy}>{confirmId === d.id ? "Confirm delete" : "Delete"}</button>}
      </>
    );
  }

  return (
    <div className={styles.page}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Documents</h1>
          <p className="page-sub">Manuals and procedures that ForgeMind searches to answer questions.</p>
        </div>
        {stats.data && (
          <p className={styles.stats}>
            <span><strong>{stats.data.documents.toLocaleString()}</strong>{stats.data.documents === 1 ? "document" : "documents"}</span>
            <span><strong>{stats.data.pages.toLocaleString()}</strong>pages</span>
            <span><strong>{stats.data.passages.toLocaleString()}</strong>searchable passages</span>
          </p>
        )}
      </header>

      {isAdmin && <div
        className={`${styles.drop}${over ? ` ${styles.over}` : ""}`}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); upload(e.dataTransfer.files); }}
      >
        <span className={styles.dropIcon}><Icon d={UPLOAD_ICON} size={26} /></span>
        <div className={styles.dropText}>
          <strong>{uploading ? `Indexing ${uploading}` : "Add to Knowledge Base"}</strong>
          <span>{uploading ? "Reading the pages and building the search index…" : "Drop PDF manuals or SOPs here, or choose files. Only PDFs are supported right now."}</span>
          {uploading && <div className={styles.progress} role="progressbar" aria-label="Indexing" />}
        </div>
        <input ref={fileInput} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => e.target.files && upload(e.target.files)} />
        <button type="button" onClick={() => fileInput.current?.click()} disabled={!!uploading}>Choose PDF files</button>
      </div>}

      <div className="toolbar">
        <div className="search grow">
          <Icon d={SEARCH_ICON} size={16} />
          <input type="search" value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search documents by name" aria-label="Search documents by name" />
        </div>
        <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort documents">
          {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>
      {types.length > 0 && (
        <div className={styles.chips} style={{ marginBottom: 16 }} role="group" aria-label="Filter by file type">
          <button type="button" className={`${styles.chip}${type === "all" ? ` ${styles.on}` : ""}`} onClick={() => setType("all")}>All types · {all.length}</button>
          {types.map(([ext, n]) => (
            <button key={ext} type="button" className={`${styles.chip}${type === ext ? ` ${styles.on}` : ""}`} onClick={() => setType(ext)}>{ext} · {n}</button>
          ))}
        </div>
      )}

      {docs.error && <div className="alert" role="alert"><p>{docs.error}</p><button type="button" onClick={refresh}>Try again</button></div>}
      {docs.loading && !docs.data && <div className={styles.grid}>{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 190 }} />)}</div>}

      {docs.data && all.length === 0 && (
        <div className="panel">
          <EmptyState icon={FILE_ICON} title="No documents yet">
            Upload an equipment manual or SOP above. Once it is indexed you can search it, ask questions about it in{" "}
            <Link href="/chat">Chat</Link> and use it for troubleshooting.
          </EmptyState>
        </div>
      )}
      {docs.data && all.length > 0 && shown.length === 0 && (
        <div className="panel"><EmptyState icon={SEARCH_ICON} title="No documents match">Try a different name or clear the file-type filter.</EmptyState></div>
      )}

      <div className={styles.grid}>
        {shown.map((d) => (
          <article key={d.id} className={styles.card}>
            <div className={styles.top}>
              <span className={styles.type} aria-hidden="true">{fileExt(d.filename)}</span>
              <div className={styles.name}>
                <h3>{d.filename}</h3>
                <span>Added {formatDate(d.uploaded_at)}</span>
              </div>
            </div>
            <div className={styles.facts}>
              {d.chunks > 0 ? <span className="badge ok">Indexed</span> : <span className="badge bad">Not indexed</span>}
              <span className="badge">{plural(d.pages, "page")}</span>
              <span className="badge">{plural(d.chunks, "passage")}</span>
            </div>
            <div className={styles.actions}>
              <button type="button" className="small" onClick={() => setOpenId(d.id)}>Preview</button>
              {actions(d)}
            </div>
          </article>
        ))}
      </div>

      <Drawer open={!!open} onClose={() => setOpenId(null)} title={open?.filename ?? ""}
              subtitle={open ? `${plural(open.pages, "page")} · ${plural(open.chunks, "passage")} · added ${formatDate(open.uploaded_at)}` : undefined}
              footer={open && (
                <>
                  <Link className="button ghost small" href={`/chat?q=${encodeURIComponent(`What are the key procedures in ${open.filename}?`)}`}>Ask in Chat</Link>
                  {actions(open)}
                </>
              )}>
        {open && <Preview key={open.id} doc={open} />}
      </Drawer>

      {toast && <div className={`toast${toast.bad ? " bad" : ""}`} role="status">{toast.text}</div>}
    </div>
  );
}