/** Small formatting helpers shared by the pages. */

export const BACKEND_HINT =
  "Can't reach the backend. From the project folder run: python -m uvicorn backend.app.main:app --port 8000";

/** A message fit to show a person for any thrown value. */
export function errorMessage(err: unknown): string {
  if (err instanceof TypeError) return BACKEND_HINT; // fetch() could not connect
  return err instanceof Error ? err.message : "Something went wrong.";
}

/** "2026-10-28" or a full timestamp -> "28 Oct 2026". Date-only strings are read as local dates. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export const hours = (n: number) => `${n.toLocaleString(undefined, { maximumFractionDigits: 1 })} h`;
export const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;
export const fileExt = (name: string) => (name.includes(".") ? name.split(".").pop()!.toUpperCase() : "FILE");
export const stripExt = (name: string) => name.replace(/\.[^.]+$/, "");
export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

/** "Atlas_Copco-GA30_Operation_Manual.pdf" -> "Atlas_Copco-GA30_Operat…" so long file names fit beside a chart bar. */
export function shortName(name: string, max = 26): string {
  const base = name.replace(/\.pdf$/i, "");
  return base.length > max ? `${base.slice(0, max - 1)}…` : base;
}