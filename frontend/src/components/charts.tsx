/** Small, dependency-free charts that share the dashboard's look: one hue, thin marks, values on the marks. */

export function ColumnChart({
  items, empty = "Nothing to show yet.",
}: {
  items: Array<{ label: string; value: number }>;
  empty?: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 0);
  if (items.length === 0 || max === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="columns">
      {items.map((i) => (
        <li key={i.label} aria-label={`${i.label}: ${i.value}`}>
          <span className="col-value">{i.value}</span>
          <span className="col-area">
            <span className="col-bar" style={{ height: `${Math.max((i.value / max) * 100, 2)}%` }} />
          </span>
          <span className="col-label">{i.label}</span>
        </li>
      ))}
    </ul>
  );
}

export function HBars({
  items, empty = "Nothing to show yet.",
}: {
  items: Array<{ label: string; sub?: string; value: number; display?: string }>;
  empty?: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 0);
  if (items.length === 0 || max === 0) return <p className="muted">{empty}</p>;
  return (
    <ul className="rank">
      {items.map((i) => (
        <li key={i.label} aria-label={`${i.label}: ${i.display ?? i.value}`}>
          <span className="rank-name">
            <strong>{i.label}</strong>
            {i.sub && <span className="muted">{i.sub}</span>}
          </span>
          <span className="rank-track">
            <span className="rank-bar" style={{ ["--ratio" as string]: i.value / max }} />
            <span className="rank-value">{i.display ?? i.value}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

/** One whole split into parts (e.g. work orders by status). Every part is named in the legend. */
export function SegmentBar({
  items, total, unit = "",
}: {
  items: Array<{ label: string; value: number; color: string }>;
  total?: number;
  unit?: string;
}) {
  const sum = total ?? items.reduce((s, i) => s + i.value, 0);
  const shown = items.filter((i) => i.value > 0);
  if (sum === 0) return <p className="muted">Nothing to show yet.</p>;
  return (
    <div>
      <div className="segbar" role="img" aria-label={shown.map((i) => `${i.label}: ${i.value}`).join(", ")}>
        {shown.map((i) => (
          <span key={i.label} title={`${i.label}: ${i.value}${unit}`} style={{ flexGrow: i.value, background: i.color }} />
        ))}
      </div>
      <ul className="legend">
        {items.map((i) => (
          <li key={i.label}>
            <span className="swatch" style={{ background: i.color }} />
            {i.label}
            <strong>{i.value}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}