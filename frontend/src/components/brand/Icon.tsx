/* ============================================================
   BAYYAN — Icon set (functional single-path line icons)
   Ported verbatim from the design handoff so glyphs match the
   prototype exactly. Stroked, 24×24, currentColor by default.
   ============================================================ */
import type { CSSProperties } from "react";

import { ICONS, type IconName } from "./IconPaths";

interface IconProps {
  name: IconName;
  size?: number;
  stroke?: number;
  color?: string;
  className?: string;
  style?: CSSProperties;
}

export default function Icon({
  name,
  size = 20,
  stroke = 2,
  color = "currentColor",
  className,
  style,
}: IconProps) {
  const d = ICONS[name] ?? ICONS.check;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={{ flex: "none", ...style }}
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}
