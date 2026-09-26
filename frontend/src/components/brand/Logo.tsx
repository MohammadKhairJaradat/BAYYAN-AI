/* ============================================================
   BAYYAN — full logo lockup (seal mark + i18n wordmark).
   Wordmark font swaps Marcellus (EN) / Aref Ruqaa (AR) via CSS.
   ============================================================ */
import { useLang } from "../../contexts/hooks";
import Mark from "./Mark";

interface LogoProps {
  size?: "sm" | "md" | "lg";
  onClick?: () => void;
  mono?: boolean;
}

export default function Logo({ size = "md", onClick, mono = false }: LogoProps) {
  const { t, dir } = useLang();
  const dims = size === "lg" ? 42 : size === "sm" ? 26 : 34;
  const isAr = dir === "rtl";
  const base = size === "lg" ? 30 : size === "sm" ? 19 : 24;
  const fs = isAr ? base * 1.16 : base;
  return (
    <div
      className="row"
      style={{ gap: 11, cursor: onClick ? "pointer" : "default" }}
      onClick={onClick}
    >
      <Mark
        size={dims}
        tone={mono ? "currentColor" : "var(--green)"}
        accent={mono ? "currentColor" : "var(--gold)"}
      />
      <span
        className="wordmark"
        style={{
          fontSize: fs,
          lineHeight: 1,
          color: "var(--ink)",
          display: "inline-block",
          paddingBottom: isAr ? 3 : 0,
        }}
      >
        {t.brand}
      </span>
    </div>
  );
}
