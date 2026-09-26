import { useEffect, useState } from "react";
import { useLang, useTaxProfile } from "../../contexts/hooks";
import { getMyUsage } from "../../services/api";
import type { UserUsage } from "../../types/api";
import { Icon } from "../brand";

interface Props {
  compact?: boolean;
  showExemptions?: boolean;
}

function fmtJD(n: number, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n);
}

export default function QuotaUsageIndicator({ compact = false, showExemptions = true }: Props) {
  const { t, fill } = useLang();
  const { calculation: calc } = useTaxProfile();
  const [usage, setUsage] = useState<UserUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const Q = t.quotas;
  const numLocale = t.dir === "rtl" ? "ar-JO" : "en-US";

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setHasError(false);
        const data = await getMyUsage();
        if (!cancelled) {
          setUsage(data);
        }
      } catch {
        if (!cancelled) {
          setHasError(true);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const docsUsed = usage?.docs.used ?? 0;
  const docsLimit = usage?.docs.limit ?? 0;
  const docsRemaining = usage?.docs.remaining ?? Math.max(0, docsLimit - docsUsed);
  const docPct = docsLimit > 0 ? Math.min(100, Math.round((docsUsed / docsLimit) * 100)) : 0;

  const tierKey = usage?.tier;
  const tierName = tierKey ? (t.chat?.tiers?.[tierKey] ?? tierKey) : "";
  const planLabel = tierName ? fill(Q.tierPlan, { tier: tierName }) : "";

  if (compact) {
    if (loading) {
      return (
        <div
          className="card card-pad"
          style={{
            padding: "14px 18px",
            border: "1px solid var(--line)",
            borderRadius: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span className="t-small" style={{ color: "var(--ink-soft)" }}>
            {Q.loadingUsage}
          </span>
        </div>
      );
    }

    if (hasError || !usage) {
      return (
        <div
          className="card card-pad"
          style={{
            padding: "14px 18px",
            border: "1px solid var(--line)",
            borderRadius: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span className="t-small" style={{ color: "var(--ink-faint)" }}>
            {Q.usageUnavailable}
          </span>
        </div>
      );
    }

    return (
      <div
        className="card card-pad"
        style={{
          padding: "14px 18px",
          border: "1px solid var(--line)",
          borderRadius: 12,
          display: "flex",
          alignItems: "center",
          gap: 16,
          justifyContent: "space-between",
          flexWrap: "wrap",
        }}
      >
        <div className="row" style={{ gap: 10 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "var(--green-tint)",
              display: "grid",
              placeItems: "center",
            }}
          >
            <Icon name="upload" size={16} color="var(--green)" />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600 }}>{Q.tierUsageTitle}</div>
            <div className="t-small" style={{ color: "var(--ink-soft)" }}>
              {docsLimit > 0
                ? fill(Q.docsUsage, { used: docsUsed, limit: docsLimit })
                : fill(Q.docsRemaining, { n: docsRemaining })}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 160 }}>
          <div
            style={{
              flex: 1,
              height: 6,
              background: "var(--line)",
              borderRadius: 999,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${docPct}%`,
                height: "100%",
                background: docsRemaining === 0 && docsLimit > 0 ? "var(--danger)" : "var(--green)",
                borderRadius: 999,
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-soft)" }}>
            {docPct}%
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: showExemptions ? "repeat(auto-fit, minmax(300px, 1fr))" : "1fr",
        gap: 16,
        marginBottom: 20,
      }}
    >
      {/* Subscription Quota Card */}
      <div
        className="card card-pad"
        style={{
          border: "1px solid var(--line)",
          borderRadius: 14,
          background: "var(--paper)",
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        <div className="row-between">
          <div className="row" style={{ gap: 10 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: 9,
                background: "var(--green-tint)",
                display: "grid",
                placeItems: "center",
              }}
            >
              <Icon name="folder" size={17} color="var(--green)" />
            </div>
            <div>
              <h4 style={{ margin: 0, fontSize: 14.5, fontWeight: 600 }}>{Q.tierUsageTitle}</h4>
              <span className="t-small" style={{ color: "var(--ink-soft)" }}>
                {loading ? Q.loadingUsage : hasError || !usage ? Q.usageUnavailable : planLabel}
              </span>
            </div>
          </div>
          {!loading && !hasError && usage && (
            <span className="chip" style={{ fontSize: 11 }}>
              {docsLimit > 0 ? fill(Q.remainingLeft, { n: docsRemaining }) : Q.active}
            </span>
          )}
        </div>

        {loading ? (
          <div style={{ paddingBlock: 12, color: "var(--ink-faint)", fontSize: 12 }}>
            {Q.loadingUsage}
          </div>
        ) : hasError || !usage ? (
          <div style={{ paddingBlock: 12, color: "var(--ink-faint)", fontSize: 12 }}>
            {Q.usageUnavailable}
          </div>
        ) : (
          <>
            <div>
              <div className="row-between" style={{ fontSize: 12.5, marginBottom: 6, color: "var(--ink-soft)" }}>
                <span>{fill(Q.docsUsage, { used: docsUsed, limit: docsLimit })}</span>
                <span style={{ fontWeight: 600 }}>{docPct}%</span>
              </div>
              <div
                style={{
                  height: 8,
                  background: "var(--line)",
                  borderRadius: 999,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${docPct}%`,
                    height: "100%",
                    background: docsRemaining === 0 && docsLimit > 0 ? "var(--danger)" : "var(--green)",
                    borderRadius: 999,
                    transition: "width 0.4s ease",
                  }}
                />
              </div>
            </div>

            <p className="t-small" style={{ margin: 0, color: "var(--ink-faint)", fontSize: 12 }}>
              {docsRemaining === 0 && docsLimit > 0 ? Q.docsLimitReached : Q.upgradeHint}
            </p>
          </>
        )}
      </div>

      {/* Jordanian Legal Tax Exemption Breakdown (Deterministic calculation values) */}
      {showExemptions && (
        <div
          className="card card-pad"
          style={{
            border: "1px solid var(--line)",
            borderRadius: 14,
            background: "var(--paper)",
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          <div className="row-between">
            <div className="row" style={{ gap: 10 }}>
              <div
                style={{
                  width: 34,
                  height: 34,
                  borderRadius: 9,
                  background: "var(--gold-tint)",
                  display: "grid",
                  placeItems: "center",
                }}
              >
                <Icon name="scale" size={17} color="var(--attention)" />
              </div>
              <div>
                <h4 style={{ margin: 0, fontSize: 14.5, fontWeight: 600 }}>
                  {Q.exemptionSummaryTitle}
                </h4>
                <span className="t-small" style={{ color: "var(--ink-soft)" }}>
                  {calc ? Q.exemptionSummarySub : Q.noCalculationSub}
                </span>
              </div>
            </div>
            {calc && (
              <span className="chip chip-gold" style={{ fontSize: 11, fontWeight: 600 }}>
                {fmtJD(calc.total_exemptions, numLocale)} {t.dir === "rtl" ? "د.أ" : "JD"}
              </span>
            )}
          </div>

          {calc ? (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 10,
                fontSize: 12,
                marginTop: 4,
              }}
            >
              <div
                style={{
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: "var(--paper-alt, rgba(0,0,0,0.02))",
                  border: "1px solid var(--line)",
                }}
              >
                <div style={{ color: "var(--ink-soft)", fontSize: 11 }}>{Q.personalLabel}</div>
                <div style={{ fontWeight: 600, color: "var(--ink)", marginTop: 2 }}>
                  {fmtJD(calc.personal_exemption, numLocale)} {t.dir === "rtl" ? "د.أ" : "JD"}
                </div>
              </div>

              <div
                style={{
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: "var(--paper-alt, rgba(0,0,0,0.02))",
                  border: "1px solid var(--line)",
                }}
              >
                <div style={{ color: "var(--ink-soft)", fontSize: 11 }}>{Q.dependentsLabel}</div>
                <div style={{ fontWeight: 600, color: "var(--ink)", marginTop: 2 }}>
                  {fmtJD(calc.family_exemption, numLocale)} {t.dir === "rtl" ? "د.أ" : "JD"}
                </div>
              </div>

              <div
                style={{
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: "var(--paper-alt, rgba(0,0,0,0.02))",
                  border: "1px solid var(--line)",
                }}
              >
                <div style={{ color: "var(--ink-soft)", fontSize: 11 }}>{Q.expensesLabel}</div>
                <div style={{ fontWeight: 600, color: "var(--ink)", marginTop: 2 }}>
                  {fmtJD(calc.expense_exemption, numLocale)} {t.dir === "rtl" ? "د.أ" : "JD"}
                </div>
              </div>

              <div
                style={{
                  padding: "8px 10px",
                  borderRadius: 8,
                  background: "var(--paper-alt, rgba(0,0,0,0.02))",
                  border: "1px solid var(--line)",
                }}
              >
                <div style={{ color: "var(--ink-soft)", fontSize: 11 }}>
                  {calc.disability_exemption > 0 ? Q.disabilityLabel : Q.totalLabel}
                </div>
                <div style={{ fontWeight: 600, color: "var(--green)", marginTop: 2 }}>
                  {fmtJD(
                    calc.disability_exemption > 0 ? calc.disability_exemption : calc.total_exemptions,
                    numLocale
                  )}{" "}
                  {t.dir === "rtl" ? "د.أ" : "JD"}
                </div>
              </div>
            </div>
          ) : (
            <div
              style={{
                padding: "12px 14px",
                borderRadius: 8,
                background: "var(--paper-alt, rgba(0,0,0,0.02))",
                border: "1px solid var(--line)",
                fontSize: 12,
                color: "var(--ink-soft)",
              }}
            >
              {Q.noCalculationSub}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
