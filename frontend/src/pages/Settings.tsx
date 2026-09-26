import { useEffect, useRef, useState } from "react";
import { useAuth } from "../contexts/hooks";
import { useTheme } from "../contexts/hooks";
import { useLang } from "../contexts/hooks";
import { updateMe } from "../services/api";
import { TaxProfileManager } from "../components/tax/TaxProfileManager";
import { Icon, type IconName } from "../components/brand";

type Preferences = {
  systemAlerts: boolean;
  calendarReminders: boolean;
};

const DEFAULT_PREFS: Preferences = {
  systemAlerts: true,
  calendarReminders: false,
};

export default function Settings() {
  const { theme, toggleTheme } = useTheme();
  const { lang, setLang, t } = useLang();
  const { user, refreshUser } = useAuth();
  const darkMode = theme === "dark";
  const S = t.settings;

  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS);
  const [savingState, setSavingState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialLoaded = useRef(false);

  useEffect(() => {
    if (!user || initialLoaded.current) return;
    const userPrefs = (user.preferences ?? {}) as Partial<Preferences>;
    setPrefs({
      systemAlerts: userPrefs.systemAlerts ?? DEFAULT_PREFS.systemAlerts,
      calendarReminders: userPrefs.calendarReminders ?? DEFAULT_PREFS.calendarReminders,
    });
    initialLoaded.current = true;
  }, [user]);

  useEffect(() => {
    if (!initialLoaded.current) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setSavingState("saving");
    debounceRef.current = setTimeout(async () => {
      try {
        await updateMe({ preferences: prefs });
        await refreshUser();
        setSavingState("saved");
        setTimeout(() => setSavingState("idle"), 1500);
      } catch {
        setSavingState("error");
      }
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs]);

  function toggle(key: keyof Preferences) {
    setPrefs((p) => ({ ...p, [key]: !p[key] }));
  }

  return (
    <div className="wrap" style={{ maxWidth: 860, paddingBlock: "40px 64px" }}>
      <div className="row-between" style={{ marginBottom: 24, alignItems: "flex-end", gap: 16 }}>
        <div>
          <h1 className="display t-h1" style={{ marginBottom: 6 }}>
            {S.title}
          </h1>
          <p className="t-body">{S.sub}</p>
        </div>
        <span className="t-small faint">
          {savingState === "saving" && t.common.loading}
          {savingState === "saved" && "✓"}
          {savingState === "error" && t.common.error}
        </span>
      </div>

      <div className="stack" style={{ ["--gap"]: "20px" } as React.CSSProperties}>
        {/* Preferences */}
        <Section icon="sun" title={S.prefTitle}>
          <Row title={S.theme} desc={darkMode ? S.dark : S.light}>
            <Toggle on={darkMode} onClick={toggleTheme} />
          </Row>
          <Row title={S.language} desc={lang === "ar" ? "العربية" : "English"}>
            <div className="row" style={{ gap: 6 }}>
              <SegBtn active={lang === "en"} onClick={() => setLang("en")} label="EN" />
              <SegBtn active={lang === "ar"} onClick={() => setLang("ar")} label="ع" />
            </div>
          </Row>
        </Section>

        {/* Notifications */}
        <Section icon="bell" title={S.notifs}>
          <Row title={S.notifs} desc={t.dir === "rtl" ? "إشعارات النظام عن حسابك وإقراراتك." : "System notifications about your account and filings."}>
            <Toggle on={prefs.systemAlerts} onClick={() => toggle("systemAlerts")} />
          </Row>
          <Row title={t.calendar.upcomingTitle} desc={t.dir === "rtl" ? "تذكير بمواعيد الضريبة." : "Sync tax deadline reminders."}>
            <Toggle on={prefs.calendarReminders} onClick={() => toggle("calendarReminders")} />
          </Row>
        </Section>

        {/* Tax profile */}
        <Section icon="scale" title={S.taxTitle}>
          <p className="t-small" style={{ marginBottom: 12 }}>
            {S.taxNote}
          </p>
          <div style={{ background: "var(--paper-2)", border: "1px solid var(--line)", borderRadius: 12, padding: 16 }}>
            <TaxProfileManager />
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({ icon, title, children }: { icon: IconName; title: string; children: React.ReactNode }) {
  return (
    <div className="card card-pad">
      <h2 className="t-h3" style={{ fontSize: 18, marginBottom: 16, display: "flex", alignItems: "center", gap: 9 }}>
        <Icon name={icon} size={19} color="var(--green)" />
        {title}
      </h2>
      <div className="stack" style={{ ["--gap"]: "12px" } as React.CSSProperties}>
        {children}
      </div>
    </div>
  );
}

function Row({ title, desc, children }: { title: string; desc?: string; children: React.ReactNode }) {
  return (
    <div
      className="row-between"
      style={{ border: "1px solid var(--line)", background: "var(--paper-2)", padding: 16, borderRadius: 12, gap: 16 }}
    >
      <div>
        <p className="t-body" style={{ color: "var(--ink)", fontWeight: 600 }}>
          {title}
        </p>
        {desc && <p className="t-small" style={{ marginTop: 2 }}>{desc}</p>}
      </div>
      {children}
    </div>
  );
}

function SegBtn({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        minWidth: 38,
        padding: "7px 12px",
        borderRadius: 9,
        fontSize: 13.5,
        fontWeight: 600,
        border: "1px solid var(--line-strong)",
        background: active ? "var(--green-tint)" : "var(--paper)",
        color: active ? "var(--green)" : "var(--ink-soft)",
      }}
    >
      {label}
    </button>
  );
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      style={{
        position: "relative",
        width: 46,
        height: 26,
        borderRadius: 999,
        border: "none",
        flex: "none",
        transition: "background .2s",
        background: on ? "var(--green)" : "var(--line-strong)",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 3,
          insetInlineStart: on ? 23 : 3,
          width: 20,
          height: 20,
          borderRadius: 999,
          background: "#FFFCF5",
          transition: "inset-inline-start .2s",
        }}
      />
    </button>
  );
}
