"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import Icon from "@/components/Icon";
import { api } from "@/lib/api";
import { errorMessage, formatDate, plural } from "@/lib/format";
import EmptyState from "@/components/EmptyState";
import { useSession } from "@/lib/session";
import { useFetch } from "@/lib/useFetch";
import type { DocumentUploaded } from "@/types";
import styles from "./upload.module.css";

const UPLOAD_ICON = "M12 16V4M7 9l5-5 5 5M4 20h16";
type State = "queued" | "uploading" | "done" | "failed";
interface Entry { id: number; file: File; state: State; error?: string; doc?: DocumentUploaded }

const size = (b: number) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const isPdf = (f: File) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf");

export default function UploadPage() {
  const { isAdmin } = useSession();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [over, setOver] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const nextId = useRef(1);
  const running = useRef(false);
  const recent = useFetch(() => api.documents(), []);
  const stats = useFetch(() => api.knowledgeStats(), []);
  useEffect(() => { document.title = "Upload | ForgeMind AI"; }, []);

  const patch = (id: number, p: Partial<Entry>) => setEntries((list) => list.map((e) => (e.id === id ? { ...e, ...p } : e)));

  function add(files: FileList | File[]) {
    const list = Array.from(files);
    const pdfs = list.filter(isPdf);
    setNotice(pdfs.length < list.length ? `${list.length - pdfs.length} file(s) skipped: only PDF files are supported.` : null);
    if (pdfs.length) setEntries((cur) => [...cur, ...pdfs.map((file) => ({ id: nextId.current++, file, state: "queued" as State }))]);
  }

  // Upload one file at a time so a failure never blocks the rest and the server is not flooded.
  // Each finished upload changes `entries`, which triggers the effect below to start the next one.
  const pump = useCallback(async (list: Entry[]) => {
    const next = list.find((e) => e.state === "queued");
    if (!next || running.current) return;
    running.current = true;
    patch(next.id, { state: "uploading" });
    try {
      const doc = await api.upload(next.file);
      patch(next.id, { state: "done", doc });
      recent.reload();
      stats.reload();
    } catch (err) {
      patch(next.id, { state: "failed", error: errorMessage(err) });
    } finally {
      running.current = false;
    }
  }, [recent, stats]);

  // Whenever the queue changes and nothing is running, start the next waiting file.
  useEffect(() => {
    if (!entries.some((e) => e.state === "uploading")) void pump(entries);
  }, [entries, pump]);

  const busy = entries.some((e) => e.state === "uploading" || e.state === "queued");
  const done = entries.filter((e) => e.state === "done").length;
  const latest = (recent.data ?? []).slice().sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at)).slice(0, 5);

  if (!isAdmin) {
    return (
      <div className="panel">
        <EmptyState icon={UPLOAD_ICON} title="Administrators only">
          Only an administrator can upload manuals. You can still read them in <Link href="/documents">Documents</Link> and ask questions in <Link href="/chat">Chat</Link>.
        </EmptyState>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Upload</h1>
          <p className="page-sub">Add manuals and procedures. Each PDF is read, split into passages and made searchable straight away.</p>
        </div>
        <Link className="button ghost" href="/documents">View all documents</Link>
      </header>

      <div className={styles.layout}>
        <div>
          <div
            className={`${styles.drop}${over ? ` ${styles.over}` : ""}`}
            role="button" tabIndex={0} aria-label="Choose PDF files to upload"
            onClick={() => input.current?.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), input.current?.click())}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); add(e.dataTransfer.files); }}
          >
            <span className={styles.dropIcon}><Icon d={UPLOAD_ICON} size={34} /></span>
            <h2>{over ? "Release to upload" : "Drop PDF files here"}</h2>
            <p>or click to browse. You can add several files at once and they will be processed one after another.</p>
            <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden
                   onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} />
          </div>
          {notice && <p className="error" role="status" style={{ marginTop: 10 }}>{notice}</p>}

          {entries.length > 0 && (
            <section className={`panel ${styles.queue}`} aria-label="Upload queue" aria-live="polite">
              <div className={styles.qHead}>
                <h2>{busy ? "Processing…" : `${done} of ${entries.length} added`}</h2>
                <span className="btn-row">
                  {entries.some((e) => e.state === "failed") && <button type="button" className="ghost small" onClick={() => setEntries((l) => l.map((e) => (e.state === "failed" ? { ...e, state: "queued", error: undefined } : e)))}>Retry failed</button>}
                  <button type="button" className="ghost small" disabled={!entries.some((e) => e.state === "done" || e.state === "failed")} onClick={() => setEntries((l) => l.filter((e) => e.state === "queued" || e.state === "uploading"))}>Clear finished</button>
                </span>
              </div>
              <ul className={styles.items}>
                {entries.map((e) => (
                  <li key={e.id} className={styles.item}>
                    <span className={styles.ext}>PDF</span>
                    <div style={{ minWidth: 0 }}>
                      <div className={styles.name} title={e.file.name}>{e.file.name}</div>
                      <div className={`${styles.meta}${e.state === "failed" ? ` ${styles.err}` : ""}`}>
                        {e.state === "queued" && `${size(e.file.size)} · waiting`}
                        {e.state === "uploading" && `${size(e.file.size)} · reading pages and building the index`}
                        {e.state === "done" && e.doc && `${plural(e.doc.pages, "page")} · ${plural(e.doc.chunks, "passage")} indexed`}
                        {e.state === "done" && e.doc?.registered_equipment && ` · added to Equipment as ${e.doc.registered_equipment.tag} (${e.doc.registered_equipment.name})`}
                        {e.state === "failed" && e.error}
                      </div>
                      {e.state === "uploading" && <div className={styles.bar} role="progressbar" aria-label={`Indexing ${e.file.name}`} />}
                    </div>
                    <div className={styles.actions}>
                      {e.state === "done" && <span className="badge ok">Indexed</span>}
                      {e.state === "failed" && <span className="badge bad">Failed</span>}
                      {e.state === "queued" && <button type="button" className="ghost small" onClick={() => setEntries((l) => l.filter((x) => x.id !== e.id))}>Remove</button>}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <aside className={styles.side}>
          <section className="panel">
            <h2 style={{ margin: "0 0 12px", fontSize: 15 }}>What happens next</h2>
            <ol className={styles.steps}>
              <li><div><strong>Text is read</strong>Every page of the PDF is extracted.</div></li>
              <li><div><strong>Split into passages</strong>Short sections that can be cited exactly.</div></li>
              <li><div><strong>Ready to use</strong>Chat and Troubleshooting can quote it immediately.</div></li>
            </ol>
          </section>

          <section className="panel">
            <h2 style={{ margin: "0 0 10px", fontSize: 15 }}>Tips for good results</h2>
            <ul className={styles.tips}>
              <li>Use PDFs with selectable text. Scanned images cannot be read.</li>
              <li>One manual per file, named clearly, for example the equipment model.</li>
              <li>Remove password protection first.</li>
            </ul>
          </section>

          <section className="panel">
            <h2 style={{ margin: "0 0 10px", fontSize: 15 }}>Knowledge base now</h2>
            {stats.data ? <p className="muted" style={{ margin: "0 0 12px" }}>{plural(stats.data.documents, "document")}, {plural(stats.data.pages, "page")}, {plural(stats.data.passages, "passage")}.</p> : null}
            {latest.length === 0 ? <p className="muted">{recent.loading ? "Loading…" : "Nothing uploaded yet."}</p> : (
              <ul className={styles.recent}>
                {latest.map((d) => <li key={d.id}><span title={d.filename}>{d.filename}</span><span className="muted">{formatDate(d.uploaded_at)}</span></li>)}
              </ul>
            )}
            <Link className="button ghost small" style={{ marginTop: 12 }} href="/knowledge-base">Browse passages</Link>
          </section>
        </aside>
      </div>
    </div>
  );
}