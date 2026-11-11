const COLORS: Record<string, string> = {
  operational: "#1f9d55",
  closed: "#1f9d55",
  maintenance: "#d69e2e",
  in_progress: "#d69e2e",
  medium: "#d69e2e",
  fault: "#e53e3e",
  open: "#e53e3e",
  critical: "#e53e3e",
  high: "#dd6b20",
  low: "#718096",
  retired: "#718096",
};

export default function StatusPill({ value }: { value: string }) {
  const color = COLORS[value] ?? "#718096";
  return (
    <span
      style={{
        background: `${color}22`,
        color,
        border: `1px solid ${color}55`,
        padding: "2px 8px",
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        textTransform: "capitalize",
        whiteSpace: "nowrap",
      }}
    >
      {value.replace(/_/g, " ")}
    </span>
  );
}