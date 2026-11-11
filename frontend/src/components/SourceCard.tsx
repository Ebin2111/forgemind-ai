"use client";

import { useState } from "react";

import type { Source } from "@/types";

const PREVIEW_CHARS = 220;

/** A cited passage: file, page, how well it matched (relative to the best match), and its text. */
export default function SourceCard({
  n, source, maxScore, active, idPrefix = "source",
}: {
  n: number;
  idPrefix?: string;
  source: Source;
  maxScore: number;
  active?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const long = source.excerpt.length > PREVIEW_CHARS;
  const share = maxScore > 0 ? Math.max(0.06, source.score / maxScore) : 0;

  return (
    <article id={`${idPrefix}-${n}`} className={`source-card${active ? " flash" : ""}`}>
      <header>
        <span className="source-n">{n}</span>
        <div className="source-title">
          <strong title={source.document}>{source.document}</strong>
          <span className="muted">Page {source.page}</span>
        </div>
        <span className="match" title="Relative match strength">
          <span className="match-bar"><span style={{ width: `${share * 100}%` }} /></span>
        </span>
      </header>
      <p>{open || !long ? source.excerpt : `${source.excerpt.slice(0, PREVIEW_CHARS).trimEnd()}…`}</p>
      {long && (
        <button type="button" className="btn-link" onClick={() => setOpen((v) => !v)}>
          {open ? "Show less" : "Show more"}
        </button>
      )}
    </article>
  );
}