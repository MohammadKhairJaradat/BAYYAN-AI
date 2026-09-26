import { useState } from "react";
import { useLang } from "../../contexts/hooks";
import { Icon } from "../brand";

interface Props {
  defaultExpanded?: boolean;
}

export default function DocumentRequirementsCard({ defaultExpanded = false }: Props) {
  const { t } = useLang();
  const [expanded, setExpanded] = useState(defaultExpanded);
  const G = t.docTypes;

  const docTypesList = [
    {
      icon: "briefcase" as const,
      title: G.salarySlipTitle,
      desc: G.salarySlipDesc,
      supports: G.salarySlipSupports,
      badgeColor: "var(--green)",
      badgeBg: "var(--green-tint)",
    },
    {
      icon: "receipt" as const,
      title: G.receiptTitle,
      desc: G.receiptDesc,
      supports: G.receiptSupports,
      badgeColor: "var(--attention)",
      badgeBg: "var(--gold-tint)",
    },
    {
      icon: "building" as const,
      title: G.statementTitle,
      desc: G.statementDesc,
      supports: G.statementSupports,
      badgeColor: "var(--brand, #1e3a2f)",
      badgeBg: "var(--green-tint2, rgba(30,58,47,0.08))",
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
              background: "var(--green-tint)",
              display: "grid",
              placeItems: "center",
              flex: "none",
            }}
          >
            <Icon name="doc" size={18} color="var(--green)" />
          </div>
          <div>
            <h3 className="t-h3" style={{ fontSize: 16, margin: 0 }}>
              {G.guideTitle}
            </h3>
            <p className="t-small" style={{ margin: "2px 0 0", color: "var(--ink-soft)" }}>
              {G.guideSubtitle}
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
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 16,
              marginBottom: 20,
            }}
          >
            {docTypesList.map((dt, idx) => (
              <div
                key={idx}
                className="card card-pad"
                style={{
                  background: "var(--paper)",
                  border: "1px solid var(--line)",
                  borderRadius: 12,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div className="row" style={{ gap: 10 }}>
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 8,
                      background: dt.badgeBg,
                      display: "grid",
                      placeItems: "center",
                      flex: "none",
                    }}
                  >
                    <Icon name={dt.icon} size={16} color={dt.badgeColor} />
                  </div>
                  <h4 style={{ margin: 0, fontSize: 14.5, fontWeight: 600 }}>{dt.title}</h4>
                </div>
                <p className="t-small" style={{ margin: 0, color: "var(--ink-soft)", flex: 1, lineHeight: 1.5 }}>
                  {dt.desc}
                </p>
                <div
                  style={{
                    padding: "8px 10px",
                    borderRadius: 8,
                    background: "var(--paper-alt, rgba(0,0,0,0.03))",
                    borderLeft: t.dir === "rtl" ? "none" : "3px solid var(--green)",
                    borderRight: t.dir === "rtl" ? "3px solid var(--green)" : "none",
                    fontSize: 12,
                    fontWeight: 500,
                    color: "var(--green)",
                  }}
                >
                  {dt.supports}
                </div>
              </div>
            ))}
          </div>

          <div
            style={{
              padding: "14px 18px",
              borderRadius: 12,
              background: "var(--green-tint)",
              border: "1px solid var(--green-tint2)",
            }}
          >
            <div className="row" style={{ gap: 8, marginBottom: 6, fontWeight: 600, fontSize: 13.5, color: "var(--green)" }}>
              <Icon name="shield" size={16} color="var(--green)" />
              <span>{G.requirementsTitle}</span>
            </div>
            <ul style={{ margin: 0, paddingInlineStart: 20, fontSize: 13, color: "var(--ink)", lineHeight: 1.6 }}>
              <li>{G.requirementsItem1}</li>
              <li>{G.requirementsItem2}</li>
              <li>{G.requirementsItem3}</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
