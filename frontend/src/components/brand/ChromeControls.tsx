/* ============================================================
   BAYYAN — language (globe) + theme (sun/moon) toggles.
   Wired to LanguageContext + ThemeContext.
   ============================================================ */
import { useLang } from "../../contexts/hooks";
import { useTheme } from "../../contexts/hooks";
import Icon from "./Icon";

function IconToggle({
  icon,
  label,
  onClick,
  title,
}: {
  icon: "globe" | "sun" | "moon";
  label?: string;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      className="row"
      title={title}
      onClick={onClick}
      style={{
        gap: 8,
        background: "var(--paper)",
        border: "1px solid var(--line)",
        color: "var(--ink)",
        padding: "9px 13px",
        borderRadius: 11,
        fontSize: 13.5,
        fontWeight: 600,
      }}
    >
      <Icon name={icon} size={17} />
      {label && <span>{label}</span>}
    </button>
  );
}

export default function ChromeControls() {
  const { t, toggleLang } = useLang();
  const { theme, toggleTheme } = useTheme();
  return (
    <div className="row" style={{ gap: 8 }}>
      <IconToggle icon="globe" label={t.langLabel} title="Language" onClick={toggleLang} />
      <IconToggle
        icon={theme === "light" ? "moon" : "sun"}
        title="Theme"
        onClick={toggleTheme}
      />
    </div>
  );
}
