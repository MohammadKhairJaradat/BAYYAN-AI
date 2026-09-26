import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getNotifications } from "../services/api";
import type { NotificationItem, NotificationSeverity } from "../types/api";
import { useLang } from "../contexts/hooks";
import { Icon } from "../components/brand";

const SEV: Record<NotificationSeverity, { dot: string; chip: string }> = {
  action: { dot: "var(--green)", chip: "chip-green" },
  warning: { dot: "var(--attention)", chip: "chip-gold" },
  info: { dot: "var(--clay)", chip: "chip-clay" },
};

export default function Notifications() {
  const { t } = useLang();
  const D = t.dashboard;
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getNotifications();
        if (!cancelled) setItems(data);
      } catch {
        if (!cancelled) setErrorMsg(t.common.error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [t.common.error]);

  return (
    <div className="wrap" style={{ maxWidth: 820, paddingBlock: "40px 64px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 className="display t-h1" style={{ marginBottom: 6 }}>
          {D.attention}
        </h1>
      </div>

      {loading ? (
        <div style={{ display: "grid", placeItems: "center", paddingBlock: 80 }}>
          <div style={{ width: 30, height: 30, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)", animation: "spin 1s linear infinite" }} />
          <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        </div>
      ) : errorMsg ? (
        <div className="card card-pad center" style={{ borderColor: "var(--danger)" }}>
          <p style={{ color: "var(--danger)" }}>{errorMsg}</p>
        </div>
      ) : items.length === 0 ? (
        <div className="card card-pad center" style={{ paddingBlock: 56 }}>
          <div style={{ width: 56, height: 56, borderRadius: 16, background: "var(--green-tint)", display: "grid", placeItems: "center", margin: "0 auto 18px" }}>
            <Icon name="bell" size={26} color="var(--green)" />
          </div>
          <h2 className="display t-h3" style={{ marginBottom: 6 }}>
            {t.dir === "rtl" ? "ما في إشعارات" : "You're all caught up"}
          </h2>
          <p className="t-small">{t.dir === "rtl" ? "لا إشعارات جديدة حالياً." : "No new notifications right now."}</p>
        </div>
      ) : (
        <ul className="stack" style={{ ["--gap"]: "12px", listStyle: "none", margin: 0, padding: 0 } as React.CSSProperties}>
          {items.map((n) => {
            const sev = SEV[n.severity];
            const body = (
              <div className="row" style={{ gap: 14, alignItems: "flex-start" }}>
                <span style={{ marginTop: 6, width: 9, height: 9, borderRadius: 999, flex: "none", background: sev.dot }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="row" style={{ gap: 10, marginBottom: 4 }}>
                    <h3 className="t-h3" style={{ fontSize: 16 }}>
                      {n.title}
                    </h3>
                    <span className={`chip ${sev.chip}`} style={{ textTransform: "capitalize" }}>
                      {n.severity}
                    </span>
                  </div>
                  <p className="t-body">{n.message}</p>
                </div>
                {n.link && <Icon name="chevron" size={16} color="var(--ink-faint)" style={{ marginTop: 6, flex: "none" }} />}
              </div>
            );
            return (
              <li key={n.id}>
                {n.link ? (
                  <Link to={n.link} className="card card-hover card-pad" style={{ display: "block" }}>
                    {body}
                  </Link>
                ) : (
                  <div className="card card-pad">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
