/* ============================================================
   BAYYAN — Mark · الختم ("The Seal")
   A tatreez diamond (the shape of an official stamp) holding the
   Arabic ن (Noon), its dot resolved as a single gold point of
   clarity. Reads as "stamped, accepted, in order".
   ============================================================ */

interface MarkProps {
  size?: number;
  tone?: string;
  accent?: string;
  /** Rounded app-icon square variant. */
  chip?: boolean;
}

function Glyph({ stroke, dot }: { stroke: string; dot: string }) {
  return (
    <g>
      <path
        d="M16 22 C 16 29, 19.5 31, 24 31 C 28.5 31, 32 29, 32 22"
        fill="none"
        stroke={stroke}
        strokeWidth="3.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M24 13.9 L26.7 16.6 L24 19.3 L21.3 16.6 Z" fill={dot} stroke="none" />
    </g>
  );
}

export default function Mark({
  size = 34,
  tone = "var(--green)",
  accent = "var(--gold)",
  chip = false,
}: MarkProps) {
  const mono = tone === "currentColor";

  if (chip) {
    return (
      <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" style={{ display: "block", flex: "none" }}>
        <rect x="0.5" y="0.5" width="47" height="47" rx="13" fill={tone} />
        <rect
          x="12.6"
          y="12.6"
          width="22.8"
          height="22.8"
          rx="5"
          transform="rotate(45 24 24)"
          fill="none"
          stroke={accent}
          strokeWidth="0.85"
          opacity="0.65"
        />
        <Glyph stroke="#FFFCF5" dot={accent} />
      </svg>
    );
  }

  if (mono) {
    return (
      <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" style={{ display: "block", flex: "none" }}>
        <rect
          x="7.8"
          y="7.8"
          width="32.4"
          height="32.4"
          rx="7"
          transform="rotate(45 24 24)"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
        />
        <Glyph stroke="currentColor" dot="currentColor" />
      </svg>
    );
  }

  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" style={{ display: "block", flex: "none" }}>
      <rect x="7.8" y="7.8" width="32.4" height="32.4" rx="7" transform="rotate(45 24 24)" fill={tone} />
      <rect
        x="12.6"
        y="12.6"
        width="22.8"
        height="22.8"
        rx="5"
        transform="rotate(45 24 24)"
        fill="none"
        stroke={accent}
        strokeWidth="0.85"
        opacity="0.6"
      />
      <Glyph stroke="#FFFCF5" dot={accent} />
    </svg>
  );
}
