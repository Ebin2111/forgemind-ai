/** ForgeMind mark and wordmark. Inline SVG: no extra request, scales with text. */
export default function Logo({ size = 44, tagline = true }: { size?: number; tagline?: boolean }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 12 }}>
      <svg width={size} height={size} viewBox="0 0 48 48" role="img" aria-label="ForgeMind AI logo" fill="none">
        <path
          d="M24 3l17.3 10v20L24 43 6.7 33V13L24 3z"
          stroke="#19d3c5"
          strokeWidth="3"
          strokeLinejoin="round"
        />
        <path d="M17 31V17h13M17 24h9" stroke="#19d3c5" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="33" cy="31" r="2.6" fill="#19d3c5" />
      </svg>
      <span style={{ display: "grid", lineHeight: 1.15, textAlign: "left" }}>
        <span style={{ fontSize: size * 0.68, fontWeight: 700, letterSpacing: "-0.01em", color: "#fff" }}>
          ForgeMind <span style={{ color: "#19d3c5" }}>AI</span>
        </span>
        {tagline && <span style={{ fontSize: size * 0.3, color: "#c9d8ea" }}>Industrial Intelligence Copilot</span>}
      </span>
    </span>
  );
}