"use client";

import { useRef } from "react";

export interface TabItem {
  id: string;
  label: string;
  count?: number;
}

/** Accessible tab strip (arrow keys move between tabs). Give each panel role="tabpanel" and aria-labelledby={tabId(prefix, id)}. */
export const tabId = (prefix: string, id: string) => `${prefix}-tab-${id}`;

export default function Tabs({
  tabs, value, onChange, prefix, label,
}: {
  tabs: TabItem[];
  value: string;
  onChange: (id: string) => void;
  prefix: string;
  label: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: React.KeyboardEvent) {
    const i = tabs.findIndex((t) => t.id === value);
    const next = e.key === "ArrowRight" ? (i + 1) % tabs.length : e.key === "ArrowLeft" ? (i - 1 + tabs.length) % tabs.length
      : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  }

  return (
    <div className="tabs" role="tablist" aria-label={label} onKeyDown={onKeyDown}>
      {tabs.map((t) => (
        <button
          key={t.id}
          ref={(el) => { refs.current[t.id] = el; }}
          id={tabId(prefix, t.id)}
          type="button"
          role="tab"
          aria-selected={t.id === value}
          tabIndex={t.id === value ? 0 : -1}
          className={`tab${t.id === value ? " active" : ""}`}
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined && <span className="tab-count">{t.count.toLocaleString()}</span>}
        </button>
      ))}
    </div>
  );
}