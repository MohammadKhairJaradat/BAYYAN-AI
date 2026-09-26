import { useState } from "react";
import { Link } from "react-router-dom";
import { useLang, useTaxProfile } from "../../contexts/hooks";
import { Icon, Button } from "../brand";

interface Props {
  documentCount?: number;
  pendingDocCount?: number;
}

export default function ProfileCompletionGuide({ documentCount = 0, pendingDocCount = 0 }: Props) {
  const { t, fill } = useLang();
  const { profile, incomeSources, deductions, calculation: calc } = useTaxProfile();
  const [collapsed, setCollapsed] = useState(false);
  const G = t.guidance;

  const numLocale = t.dir === "rtl" ? "ar-JO" : "en-US";
  const fmtJD = (n: number) => new Intl.NumberFormat(numLocale, { maximumFractionDigits: 0 }).format(n);

  // Evaluation of 4 steps:
  const step1Done = profile !== null && Boolean(profile.residency_status);
  const step2Done = incomeSources.length > 0;
  const step3Done = deductions.length > 0 || documentCount > 0;
  const step4Done = calc !== null;

  const completedStepsCount = [step1Done, step2Done, step3Done, step4Done].filter(Boolean).length;
  const progressPct = Math.round((completedStepsCount / 4) * 100);

  const steps = [
    {
      num: 1,
      title: G.step1Title,
      desc: G.step1Desc,
      cta: G.step1Cta,
      to: "/settings",
      done: step1Done,
      icon: "user" as const,
      detail: profile
        ? `${profile.tax_year} · ${profile.marital_status === "married" ? t.settings.married : t.settings.single} (${profile.num_dependents} ${t.settings.deps})`
        : null,
    },
    {
      num: 2,
      title: G.step2Title,
      desc: G.step2Desc,
      cta: G.step2Cta,
      to: "/settings",
      done: step2Done,
      icon: "briefcase" as const,
      detail: step2Done
        ? fill(G.incomeSourcesDetail, { count: incomeSources.length })
        : null,
    },
    {
      num: 3,
      title: G.step3Title,
      desc: G.step3Desc,
      cta: G.step3Cta,
      to: "/files",
      done: step3Done,
      icon: "folder" as const,
      detail:
        documentCount > 0 || deductions.length > 0
          ? fill(G.docsDetail, { count: documentCount, deductions: deductions.length })
          : null,
    },
    {
      num: 4,
      title: G.step4Title,
      desc: G.step4Desc,
      cta: G.step4Cta,
      to: calc ? "/advisor" : "/settings",
      done: step4Done,
      icon: "chart" as const,
      detail: step4Done
        ? fill(G.netDueDetail, {
            due: fmtJD(calc?.net_tax_due ?? 0),
            refund: fmtJD(calc?.refund_due ?? 0),
          })
        : null,
    },
  ];

  const nextStep = steps.find((s) => !s.done);

  return (
    <div
      className="card"
      style={{
        border: "1px solid var(--line)",
        borderRadius: 16,
        overflow: "hidden",
        background: "var(--paper)",
        marginBottom: 24,
      }}
    >
      {/* Header */}
      <button
        type="button"
        className="row-between"
        style={{
          width: "100%",
          padding: "16px 22px",
          background: "var(--paper-alt, var(--green-tint2))",
          borderTop: "none",
          borderLeft: "none",
          borderRight: "none",
          borderBottom: collapsed ? "none" : "1px solid var(--line)",
          cursor: "pointer",
          textAlign: "inherit",
          font: "inherit",
        }}
        onClick={() => setCollapsed(!collapsed)}
        aria-expanded={!collapsed}
        aria-label={collapsed ? t.common.expand : t.common.collapse}
      >
        <div className="row" style={{ gap: 14 }}>
          <div
            style={{
              width: 40,
              height: 40,
              borderRadius: 12,
              background: progressPct === 100 ? "var(--green)" : "var(--green-tint)",
              display: "grid",
              placeItems: "center",
              flex: "none",
            }}
          >
            <Icon
              name={progressPct === 100 ? "check" : "spark"}
              size={20}
              color={progressPct === 100 ? "white" : "var(--green)"}
            />
          </div>
          <div>
            <div className="row" style={{ gap: 10, alignItems: "center" }}>
              <h3 className="t-h3" style={{ fontSize: 16.5, margin: 0 }}>
                {G.completionTitle}
              </h3>
              <span
                className={progressPct === 100 ? "chip chip-green" : "chip chip-gold"}
                style={{ fontSize: 11.5, fontWeight: 700 }}
              >
                {progressPct}% {G.completed}
              </span>
            </div>
            <p className="t-small" style={{ margin: "3px 0 0", color: "var(--ink-soft)" }}>
              {G.completionSubtitle}
            </p>
          </div>
        </div>

        <div className="row" style={{ gap: 12 }}>
          {nextStep && !collapsed && (
            <span
              className="max-md:hidden t-small"
              style={{
                color: "var(--attention)",
                fontWeight: 600,
                background: "var(--gold-tint)",
                padding: "4px 10px",
                borderRadius: 8,
              }}
            >
              {G.nextStep} {nextStep.title}
            </span>
          )}
          <div
            style={{
              transform: collapsed ? "rotate(90deg)" : "rotate(-90deg)",
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
        </div>
      </button>

      {/* Progress meter bar */}
      <div style={{ height: 4, background: "var(--line)", width: "100%" }}>
        <div
          style={{
            height: "100%",
            width: `${progressPct}%`,
            background: progressPct === 100 ? "var(--positive)" : "var(--green)",
            transition: "width 0.4s ease",
          }}
        />
      </div>

      {/* Body steps */}
      {!collapsed && (
        <div style={{ padding: 22 }}>
          {pendingDocCount > 0 && (
            <div
              className="row-between"
              style={{
                padding: "12px 16px",
                borderRadius: 12,
                background: "var(--gold-tint)",
                border: "1px solid var(--attention)",
                marginBottom: 18,
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div className="row" style={{ gap: 10 }}>
                <Icon name="bolt" size={18} color="var(--attention)" />
                <span className="t-small" style={{ fontWeight: 600, color: "var(--ink)" }}>
                  {t.dashboard.pendingDocsBanner
                    ? fill(t.dashboard.pendingDocsBanner, { count: pendingDocCount })
                    : `${pendingDocCount} document(s) pending AI processing.`}
                </span>
              </div>
              <Link to="/files">
                <Button variant="primary" style={{ padding: "6px 14px", fontSize: 13 }}>
                  {t.dashboard.processNow ?? "Process now"} →
                </Button>
              </Link>
            </div>
          )}

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
              gap: 14,
            }}
          >
            {steps.map((st) => (
              <div
                key={st.num}
                style={{
                  border: "1px solid " + (st.done ? "var(--green-tint2)" : "var(--line)"),
                  background: st.done ? "var(--paper)" : "var(--paper-alt, rgba(0,0,0,0.01))",
                  borderRadius: 12,
                  padding: 16,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  gap: 12,
                  position: "relative",
                }}
              >
                <div>
                  <div className="row-between" style={{ marginBottom: 8 }}>
                    <div className="row" style={{ gap: 8 }}>
                      <div
                        style={{
                          width: 26,
                          height: 26,
                          borderRadius: 7,
                          background: st.done ? "var(--green-tint)" : "var(--paper-alt)",
                          display: "grid",
                          placeItems: "center",
                        }}
                      >
                        <Icon
                          name={st.done ? "check" : st.icon}
                          size={14}
                          color={st.done ? "var(--green)" : "var(--ink-soft)"}
                        />
                      </div>
                      <span
                        style={{
                          fontWeight: 700,
                          fontSize: 13.5,
                          color: st.done ? "var(--green)" : "var(--ink)",
                        }}
                      >
                        {st.title}
                      </span>
                    </div>
                  </div>
                  <p
                    className="t-small"
                    style={{
                      margin: 0,
                      color: "var(--ink-soft)",
                      lineHeight: 1.5,
                      fontSize: 12.5,
                    }}
                  >
                    {st.desc}
                  </p>
                  {st.detail && (
                    <div
                      style={{
                        marginTop: 8,
                        fontSize: 11.5,
                        fontWeight: 600,
                        color: "var(--green)",
                      }}
                    >
                      ✓ {st.detail}
                    </div>
                  )}
                </div>

                <div style={{ marginTop: "auto", paddingTop: 8 }}>
                  <Link to={st.to}>
                    <Button
                      variant={st.done ? "quiet" : "primary"}
                      style={{
                        width: "100%",
                        justifyContent: "center",
                        fontSize: 12.5,
                        padding: "6px 12px",
                      }}
                    >
                      {st.cta}
                    </Button>
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
