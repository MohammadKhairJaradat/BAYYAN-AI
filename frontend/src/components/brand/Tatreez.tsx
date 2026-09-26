/* ============================================================
   BAYYAN — heritage ornament: tatreez net, ribbon border,
   seven-pointed star, mosaic divider band.
   ============================================================ */
import { useMemo, type CSSProperties } from "react";

let _tatSeq = 0;

interface TatreezProps {
  scale?: number;
  tone?: string;
  opacity?: number;
  fade?: boolean;
  heritage?: boolean;
  style?: CSSProperties;
}

/** Subtle tessellating-diamond + cross-stitch texture. Theme-aware via --tile-*. */
export function Tatreez({
  scale = 30,
  tone,
  opacity = 0.42,
  fade = false,
  heritage = false,
  style,
}: TatreezProps) {
  const id = useMemo(() => "tat-" + ++_tatSeq, []);
  const c1 = tone || "var(--tile-ink)";
  const c2 = heritage ? "var(--tile-clay)" : tone || "var(--tile-ink)";
  const c3 = heritage ? "var(--tile-gold)" : tone || "var(--tile-ink)";
  const s = scale;
  const h = s / 2;
  const dia = `M${h} 0L${s} ${h}L${h} ${s}L0 ${h}Z`;
  const inner = `M${h} ${(s * 0.33).toFixed(1)}L${(s * 0.67).toFixed(1)} ${h}L${h} ${(s * 0.67).toFixed(1)}L${(s * 0.33).toFixed(1)} ${h}Z`;
  const star = `M${h} ${h - 3.2}L${h + 1.1} ${h - 1.1}L${h + 3.2} ${h}L${h + 1.1} ${h + 1.1}L${h} ${h + 3.2}L${h - 1.1} ${h + 1.1}L${h - 3.2} ${h}L${h - 1.1} ${h - 1.1}Z`;
  const fadeStyle: CSSProperties | undefined = fade
    ? {
        WebkitMaskImage: "radial-gradient(120% 78% at 50% 0%, #000 32%, transparent 80%)",
        maskImage: "radial-gradient(120% 78% at 50% 0%, #000 32%, transparent 80%)",
      }
    : undefined;
  return (
    <svg
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        opacity: `calc(${opacity} * var(--net-mult, 1))`,
        pointerEvents: "none",
        ...fadeStyle,
        ...style,
      }}
    >
      <defs>
        <pattern id={id} width={s} height={s} patternUnits="userSpaceOnUse">
          <g fill="none" strokeWidth="1">
            <path d={dia} stroke={c1} />
            <path d={inner} stroke={c2} />
          </g>
          <path d={star} fill={c3} />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill={`url(#${id})`} />
    </svg>
  );
}

interface SevenStarProps {
  size?: number;
  color?: string;
  style?: CSSProperties;
}

/** Jordanian seven-pointed star (flag motif). */
export function SevenStar({ size = 16, color = "currentColor", style }: SevenStarProps) {
  const pts: string[] = [];
  for (let i = 0; i < 14; i++) {
    const r = i % 2 === 0 ? 11 : 4.7;
    const a = (Math.PI / 7) * i - Math.PI / 2;
    pts.push(`${(12 + r * Math.cos(a)).toFixed(2)} ${(12 + r * Math.sin(a)).toFixed(2)}`);
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ flex: "none", ...style }}>
      <polygon points={pts.join(" ")} fill={color} />
    </svg>
  );
}

interface TatreezBorderProps {
  height?: number;
  color?: string;
  style?: CSSProperties;
}

/** تطريز embroidery ribbon — slim heritage strip (diamonds + chevrons). */
export function TatreezBorder({ height = 26, color = "#B23A2E", style }: TatreezBorderProps) {
  const tile = encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' width='40' height='34' viewBox='0 0 40 34'>` +
      `<g fill='none' stroke='${color}' stroke-width='1.6'>` +
      `<path d='M20 4 L31 17 L20 30 L9 17 Z'/>` +
      `<path d='M20 11 L26 17 L20 23 L14 17 Z'/>` +
      `<path d='M0 17 L6 11 M0 17 L6 23 M40 17 L34 11 M40 17 L34 23'/>` +
      `</g><circle cx='20' cy='17' r='1.7' fill='${color}'/></svg>`
  );
  return (
    <div
      aria-hidden="true"
      style={{
        height,
        backgroundImage: `url("data:image/svg+xml,${tile}")`,
        backgroundSize: `40px ${Math.min(height, 34)}px`,
        backgroundRepeat: "repeat-x",
        backgroundPosition: "center",
        ...style,
      }}
    />
  );
}

interface MosaicBandProps {
  count?: number;
  style?: CSSProperties;
  onDark?: boolean;
}

/** Decorative tatreez divider band (fading diamonds, gold center). */
export function MosaicBand({ count = 13, style, onDark = false }: MosaicBandProps) {
  const mid = (count - 1) / 2;
  return (
    <div className="row" style={{ gap: 7, justifyContent: "center", ...style }} aria-hidden="true">
      {Array.from({ length: count }).map((_, i) => {
        const d = Math.abs(i - mid);
        const isMid = d < 1.1;
        const fade = 0.28 + 0.72 * (1 - d / (mid + 0.5));
        return (
          <span
            key={i}
            style={{
              width: isMid ? 10 : 8,
              height: isMid ? 10 : 8,
              borderRadius: 2,
              transform: "rotate(45deg)",
              background: isMid ? "var(--gold)" : onDark ? "#FFFCF5" : "var(--green)",
              opacity: isMid ? 1 : fade,
            }}
          />
        );
      })}
    </div>
  );
}
