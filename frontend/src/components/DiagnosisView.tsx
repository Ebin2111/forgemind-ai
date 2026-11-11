"use client";

import { useState } from "react";

import AnswerText from "@/components/AnswerText";
import Icon from "@/components/Icon";
import SourceCard from "@/components/SourceCard";
import StatusPill from "@/components/StatusPill";
import { formatDate, hours } from "@/lib/format";
import type { TroubleshootResponse } from "@/types";

interface Section { title: string; body: string }

/** Splits "## Heading" sections out of an AI answer. Text before the first heading is kept as `intro`. */
export function splitSections(text: string): { intro: string; sections: Section[] } {
  const sections: Section[] = [];
  let intro: string[] = [];
  let current: { title: string; lines: string[] } | null = null;
  for (const line of text.split(/\r?\n/)) {
    const h = /^#{2,3}\s+(.+?)\s*$/.exec(line.trim());
    if (h) {
      if (current) sections.push({ title: current.title, body: current.lines.join("\n").trim() });
      current = { title: h[1].replace(/[*:]+/g, "").trim(), lines: [] };
    } else if (current) current.lines.push(line);
    else intro.push(line);
  }
  if (current) sections.push({ title: current.title, body: current.lines.join("\n").trim() });
  return { intro: intro.join("\n").trim(), sections: sections.filter((s) => s.body) };
}

const ICONS = {
  cause: "M12 9v4M12 17h.01M10.3 3.9L2.4 18a2 2 0 001.7 3h15.8a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z",
  check: "M9 11l3 3 8-8M20 12v7a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2h9",
  fix: "M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z",
  note: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z",
};
const iconFor = (title: string) => {
  const t = title.toLowerCase();
  return /cause|reason|why/.test(t) ? ICONS.cause : /check|step|inspect|diagnos/.test(t) ? ICONS.check : /action|fix|solution|correct|repair|remed/.test(t) ? ICONS.fix : ICONS.note;
};

const generatedLabel = (g: string) => (g === "extractive" ? "Document excerpts" : g === "none" ? "No matching documents" : g);

/** The result of a diagnosis: causes, checks and fixes from the manuals, similar past jobs, and the cited sources. */
export default function DiagnosisView({ result }: { result: TroubleshootResponse }) {
  const [flash, setFlash] = useState<number | null>(null);
  const { intro, sections } = splitSections(result.answer);
  const maxScore = Math.max(0, ...result.sources.map((s) => s.score));

  function cite(n: number) {
    document.getElementById(`ref-${n}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(n);
    setTimeout(() => setFlash(null), 1500);
  }

  return (
    <div className="diag fade-up">
      <div className="diag-meta">
        <span className="badge accent">{generatedLabel(result.generated_by)}</span>
        <span className="muted">{result.retrieval_mode} search · {(result.latency_ms / 1000).toFixed(1)} s</span>
      </div>

      {result.generated_by === "extractive" && (
        <p className="diag-note">The AI model is not available, so this shows the most relevant excerpts from your documents instead of a written diagnosis.</p>
      )}

      {sections.length === 0 ? (
        <section className="diag-card"><h3><Icon d={ICONS.note} size={18} />Diagnosis</h3><AnswerText text={result.answer} onCite={cite} /></section>
      ) : (
        <>
          {intro && <section className="diag-card"><AnswerText text={intro} onCite={cite} /></section>}
          {sections.map((s) => (
            <section key={s.title} className="diag-card">
              <h3><Icon d={iconFor(s.title)} size={18} />{s.title}</h3>
              <AnswerText text={s.body} onCite={cite} />
            </section>
          ))}
        </>
      )}

      {result.related_work_orders.length > 0 && (
        <section className="diag-card">
          <h3><Icon d="M12 8v5l3 2M3 12a9 9 0 1018 0 9 9 0 00-18 0z" size={18} />Related past issues</h3>
          <ul className="past">
            {result.related_work_orders.map((w) => (
              <li key={w.wo_number}>
                <div className="past-top">
                  <strong>{w.wo_number}</strong>
                  <StatusPill value={w.priority} />
                  <StatusPill value={w.status} />
                  <span className="muted">{formatDate(w.created_at)}{w.downtime_hours > 0 ? ` · ${hours(w.downtime_hours)} downtime` : ""}</span>
                </div>
                <p>{w.title}</p>
                {w.description && <p className="muted">{w.description}</p>}
                {w.matched_terms.length > 0 && (
                  <p className="terms">{w.matched_terms.map((t) => <span key={t} className="badge">{t}</span>)}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {result.sources.length > 0 && (
        <section className="diag-card">
          <h3><Icon d="M6 3h9l5 5v13H6zM14 3v6h6M9 13h8M9 17h8" size={18} />Manuals and SOP references</h3>
          <div className="source-list">
            {result.sources.map((s, i) => (
              <SourceCard key={i} n={i + 1} source={s} maxScore={maxScore} idPrefix="ref" active={flash === i + 1} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}