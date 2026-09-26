import { useState } from "react";
import { useLang } from "../../contexts/hooks";
import { Icon } from "../brand";

interface Props {
  defaultExpanded?: boolean;
}

export default function DocumentStatusExplainer({ defaultExpanded = false }: Props) {
  const { t } = useLang();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const S = t.docStatus;

  const statuses = [
    {
      key: "pending",
      title: S.pendingTitle,
      desc: S.pendingDesc,
      action: S.pendingAction,
      chipClass: "chip chip-gold",
      icon: "bolt" as const,
      color: "var(--attention)",
    },
    {
      key: "processing",
      title: S.processingTitle,
      desc: S.processingDesc,
      action: null,
      chipClass: "chip",
      icon: "refresh" as const,
      color: "var(--green)",
    },
    {
      key: "processed",
      title: S.processedTitle,
      desc: S.processedDesc,
      action: null,
      chipClass: "chip chip-green",
      icon: "check" as const,
      color: "var(--positive)",
    },
    {
      key: "failed",
      title: S.failedTitle,
      desc: S.failedDesc,
      action: S.failedAction,
      chipClass: "chip chip-clay",
      icon: "x" as const,
      color: "var(--danger)",
    },
  ];

  return (
    <div
      className="card"
      style={{
        border: "1px solid var(--line)",
        borderRadius: 16,
        overflow: "hidden",
        background: "var(--paper)",
        marginBottom: 20,
      }}
    >
      <button
        type="button"
        className="row-between"
        style={{
          width: "100%",
          padding: "16px 20px",
          background: "var(--paper-alt, var(--green-tint2))",
          cursor: "pointer",
          border: "none",
          textAlign: "inherit",
          font: "inherit",
        }}
        onClick={() => setExpanded(!expanded)}
        aria-expanded={expanded}
        aria-label={expanded ? t.common.collapse : t.common.expand}
      >
        <div className="row" style={{ gap: 12 }}>
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 10,
              background: "var(--gold-tint)",
              display: "grid",
              placeItems: "center",
              flex: "none",
            }}
          >
            <Icon name="bolt" size={18} color="var(--attention)" />
          </div>
          <div>
            <h3 className="t-h3" style={{ fontSize: 16, margin: 0 }}>
              {S.statusTitle}
            </h3>
            <p className="t-small" style={{ margin: "2px 0 0", color: "var(--ink-soft)" }}>
              {S.statusSubtitle}
            </p>
          </div>
        </div>
        <div
          style={{
            transform: expanded ? "rotate(-90deg)" : "rotate(90deg)",
            transition: "transform 0.2s ease",
            padding: 8,
            display: "grid",
            placeItems: "center",
            color: "var(--ink-soft)",
          }}
          aria-hidden="true"
        >
          <Icon name="chevron" size={16} />
        </div>
      </button>

      {expanded && (
        <div style={{ padding: "20px" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: 14,
            }}
          >
            {statuses.map((st) => (
              <div
                key={st.key}
                style={{
                  padding: 14,
                  borderRadius: 12,
                  border: "1px solid var(--line)",
                  background: "var(--paper)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div className="row-between">
                  <span className={st.chipClass}>{st.title}</span>
                  <Icon name={st.icon} size={15} color={st.color} />
                </div>
                <p className="t-small" style={{ margin: 0, color: "var(--ink-soft)", lineHeight: 1.5, flex: 1 }}>
                  {st.desc}
                </p>
                {st.action && (
                  <div
                    style={{
                      fontSize: 11.5,
                      fontWeight: 600,
                      color: st.color,
                      padding: "6px 8px",
                      borderRadius: 6,
                      background: "rgba(0,0,0,0.02)",
                    }}
                  >
                    {st.action}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
