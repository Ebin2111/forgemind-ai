/** The ForgeMind mark as a living orb: it breathes while idle and its ring spins while the assistant is working. */
export default function Orb({ size = 40, thinking = false }: { size?: number; thinking?: boolean }) {
  return (
    <span className={`orb${thinking ? " thinking" : ""}`} style={{ width: size, height: size }} aria-hidden="true">
      <span className="orb-ring" />
      <span className="orb-ring r2" />
      <span className="orb-core" />
      <span className="orb-arc" />
      <svg viewBox="0 0 48 48" fill="none">
        <path d="M24 3l17.3 10v20L24 43 6.7 33V13L24 3z" stroke="#19d3c5" strokeWidth="3" strokeLinejoin="round" />
        <path d="M17 31V17h13M17 24h9" stroke="#19d3c5" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="33" cy="31" r="2.6" fill="#19d3c5" />
      </svg>
    </span>
  );
}