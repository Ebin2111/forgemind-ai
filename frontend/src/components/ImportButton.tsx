"use client";

import { useRef, useState } from "react";

import Icon from "@/components/Icon";
import { errorMessage } from "@/lib/format";
import type { ImportResult } from "@/types";

const UPLOAD_ICON = "M12 16V4M7 9l5-5 5 5M4 20h16";

/**
 * "Import" button: pick a .csv or .json file, send it, and report how many rows were added or skipped.
 * `columns` is shown as a hint so people know what the file must contain.
 */
export default function ImportButton({
  label, columns, run, onDone,
}: {
  label: string;
  columns: string;
  run: (file: File) => Promise<ImportResult>;
  onDone: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string; errors: string[] } | null>(null);

  async function pick(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setResult(null);
    try {
      const r = await run(file);
      setResult({
        ok: r.added > 0,
        text: `${r.added} added${r.skipped ? `, ${r.skipped} skipped` : ""}.`,
        errors: r.errors,
      });
      if (r.added > 0) onDone();
    } catch (err) {
      setResult({ ok: false, text: errorMessage(err), errors: [] });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = ""; // allow picking the same file again
    }
  }

  return (
    <>
      <button type="button" className="ghost" disabled={busy} onClick={() => input.current?.click()} title={`Columns: ${columns}`}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Icon d={UPLOAD_ICON} size={16} />{busy ? "Importing…" : label}
        </span>
      </button>
      <input ref={input} type="file" accept=".csv,.json,text/csv,application/json" hidden onChange={(e) => pick(e.target.files?.[0])} />
      {result && (
        <div className="toast" role="status" onClick={() => setResult(null)} style={{ cursor: "pointer", borderColor: result.ok ? undefined : "#7a3b38" }}>
          <strong>{result.text}</strong>
          {result.errors.slice(0, 5).map((e) => <div key={e} className="muted" style={{ fontSize: 13 }}>{e}</div>)}
          {result.errors.length > 5 && <div className="muted" style={{ fontSize: 13 }}>…and {result.errors.length - 5} more.</div>}
          <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>Expected columns: {columns}. Click to dismiss.</div>
        </div>
      )}
    </>
  );
}