import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useLang, useTaxProfile } from "../../contexts/hooks";
import { previewTaxWorkspace } from "../../services/api";
import type { TaxWorkspacePreview } from "../../types/api";
import { Icon, Button } from "../brand";

function parseMoney(val: unknown): number {
  if (typeof val === "number") return val;
  if (typeof val === "string") {
    const parsed = parseFloat(val);
    return isNaN(parsed) ? 0 : parsed;
  }
  return 0;
}

export default function TaxYearSummary() {
  const { t, fill } = useLang();
  const D = t.dashboard;
  const isAr = t.dir === "rtl";
  const numLocale = isAr ? "ar-JO" : "en-US";
  const curr = isAr ? "د.أ" : "JD";

  const {
    currentYear,
    availableYears,
    selectYear,
    profile,
    version: profileVersion,
  } = useTaxProfile();

  const [workspace, setWorkspace] = useState<TaxWorkspacePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!profile) return;
    const requestId = ++requestIdRef.current;
    let active = true;

    Promise.resolve().then(() => {
      if (active && requestIdRef.current === requestId) {
        setLoading(true);
        setFetchError(null);
      }
    });

    previewTaxWorkspace(currentYear)
      .then((data) => {
        if (active && requestIdRef.current === requestId) {
          setWorkspace(data);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (active && requestIdRef.current === requestId) {
          setWorkspace(null);
          setLoading(false);
          const status = (err as { response?: { status?: number } })?.response?.status;
          if (status !== 404) {
            setFetchError(t.common.error);
          }
        }
      });

    return () => {
      active = false;
      requestIdRef.current += 1;
    };
  }, [currentYear, profile, profileVersion, t.common.error]);

  const fmtJD = (n: number) => `${new Intl.NumberFormat(numLocale, { maximumFractionDigits: 0 }).format(n)} ${curr}`;

  if (!profile) {
    return null;
  }

  const latestRun = workspace?.latest_run ?? null;
  const preview = workspace?.preview ?? {};
  const rulesetId = (preview.ruleset_id as string) || "bayyan-demo-legacy-v1";
  const currentVersion = workspace?.profile_version ?? profile.version ?? 1;

  const grossIncome = parseMoney(preview.gross_income);
  const totalExemptions = parseMoney(preview.total_exemptions);
  const taxableIncome = parseMoney(preview.taxable_income);
  const netTaxDue = parseMoney(preview.net_tax_due);
  const refundDue = parseMoney(preview.refund_due);
  const isZeroIncome = grossIncome === 0;

  const formatSavedDate = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString(numLocale, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return isoStr;
    }
  };

  return (
    <div
      className="card card-pad"
      data-testid="tax-year-summary-card"
      style={{
        border: "1px solid var(--line)",
        borderRadius: 16,
        background: "var(--paper)",
        marginBottom: 24,
      }}
    >
      {/* Header & Year Selector */}
      <div
        className="row-between"
        style={{
          flexWrap: "wrap",
          gap: 12,
          paddingBottom: 16,
          borderBottom: "1px solid var(--line)",
          marginBottom: 16,
        }}
      >
        <div className="row" style={{ gap: 12, alignItems: "center" }}>
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
            <Icon name="calendar" size={18} color="var(--green)" />
          </div>
          <div>
            <h2 className="t-h3" style={{ margin: 0, fontSize: 18 }}>
              {D.taxYearSummaryTitle}
            </h2>
            <div className="row" style={{ gap: 8, marginTop: 4, flexWrap: "wrap" }}>
              <span
                style={{
                  fontSize: 11,
                  padding: "2px 8px",
                  borderRadius: 6,
                  background: "var(--paper-alt, var(--line))",
                  color: "var(--ink-soft)",
                  fontWeight: 600,
                }}
              >
                {fill(D.profileVersionBadge, { version: currentVersion })}
              </span>
              <span
                style={{
                  fontSize: 11,
                  padding: "2px 8px",
                  borderRadius: 6,
                  background: "var(--paper-alt, var(--line))",
                  color: "var(--ink-soft)",
                  fontWeight: 500,
                }}
              >
                {fill(D.demoRulesetBadge, { ruleset: rulesetId })}
              </span>
              <span
                style={{
                  fontSize: 11,
                  padding: "2px 8px",
                  borderRadius: 6,
                  background: "var(--gold-tint)",
                  color: "var(--attention)",
                  fontWeight: 500,
                }}
              >
                {D.notOfficialFilingNotice}
              </span>
            </div>
          </div>
        </div>

        {/* Year switch selector */}
        {availableYears.length > 1 && (
          <div className="row" style={{ gap: 8, alignItems: "center" }}>
            <label
              htmlFor="tax-year-select"
              className="t-small"
              style={{ color: "var(--ink-soft)", fontWeight: 500 }}
            >
              {D.taxYearSelectorLabel}:
            </label>
            <select
              id="tax-year-select"
              aria-label={D.taxYearSelectorLabel}
              value={currentYear}
              onChange={(e) => selectYear(Number(e.target.value))}
              style={{
                padding: "6px 12px",
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "var(--paper)",
                color: "var(--ink)",
                fontWeight: 600,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              {availableYears.map((yr) => (
                <option key={yr} value={yr}>
                  {yr}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {loading ? (
        <div style={{ padding: "24px 0", textAlign: "center", color: "var(--ink-soft)" }}>
          <span className="t-small">{t.common.loading}</span>
        </div>
      ) : fetchError ? (
        <div
          style={{
            padding: 12,
            borderRadius: 8,
            background: "var(--danger-tint, #fef2f2)",
            color: "var(--danger)",
            fontSize: 13,
            marginBottom: 16,
          }}
        >
          {fetchError}
        </div>
      ) : (
        <>
          {/* Calculation Run Status Banner */}
          <div
            data-testid="tax-run-status-banner"
            style={{
              padding: "12px 16px",
              borderRadius: 12,
              marginBottom: 18,
              border: `1px solid ${
                !latestRun
                  ? "var(--line)"
                  : latestRun.stale
                    ? "var(--attention)"
                    : "var(--green)"
              }`,
              background: !latestRun
                ? "var(--paper-alt, #f9fafb)"
                : latestRun.stale
                  ? "var(--gold-tint)"
                  : "var(--green-tint)",
            }}
          >
            <div className="row-between" style={{ flexWrap: "wrap", gap: 8, marginBottom: 4 }}>
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <span
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: 999,
                    background: !latestRun
                      ? "var(--ink-faint)"
                      : latestRun.stale
                        ? "var(--attention)"
                        : "var(--green)",
                  }}
                />
                <strong
                  className="t-small"
                  style={{
                    color: !latestRun
                      ? "var(--ink)"
                      : latestRun.stale
                        ? "var(--attention)"
                        : "var(--green)",
                  }}
                >
                  {!latestRun
                    ? D.noRunLabel
                    : latestRun.stale
                      ? D.staleRunLabel
                      : D.upToDateLabel}
                </strong>
              </div>
              {latestRun?.created_at && (
                <span className="t-small" style={{ color: "var(--ink-soft)", fontSize: 11.5 }}>
                  {fill(D.lastSavedAt, { date: formatSavedDate(latestRun.created_at) })}
                </span>
              )}
            </div>
            <p className="t-small" style={{ margin: 0, color: "var(--ink-soft)" }}>
              {!latestRun
                ? D.noRunDesc
                : latestRun.stale
                  ? fill(D.staleRunDesc, {
                      savedVersion: latestRun.profile_version,
                      currentVersion,
                    })
                  : fill(D.upToDateDesc, { version: currentVersion })}
            </p>
          </div>

          {/* Zero-Income Notice if applicable */}
          {isZeroIncome && (
            <div
              data-testid="zero-income-notice"
              style={{
                padding: "10px 14px",
                borderRadius: 10,
                background: "var(--paper-alt, #f9fafb)",
                border: "1px dashed var(--line)",
                marginBottom: 16,
                fontSize: 12.5,
                color: "var(--ink-soft)",
              }}
            >
              {D.zeroIncomeNotice}
            </div>
          )}

          {/* Facts Grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 12,
              marginBottom: 18,
            }}
            className="max-md:!grid-cols-2"
          >
            <div
              className="card card-pad"
              style={{ padding: 12, background: "var(--paper-alt, #f9fafb)", border: "none" }}
            >
              <div className="t-eyebrow" style={{ fontSize: 10, marginBottom: 4 }}>
                {D.previewGross}
              </div>
              <div className="num" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtJD(grossIncome)}
              </div>
            </div>

            <div
              className="card card-pad"
              style={{ padding: 12, background: "var(--paper-alt, #f9fafb)", border: "none" }}
            >
              <div className="t-eyebrow" style={{ fontSize: 10, marginBottom: 4 }}>
                {D.previewExemptions}
              </div>
              <div className="num" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtJD(totalExemptions)}
              </div>
            </div>

            <div
              className="card card-pad"
              style={{ padding: 12, background: "var(--paper-alt, #f9fafb)", border: "none" }}
            >
              <div className="t-eyebrow" style={{ fontSize: 10, marginBottom: 4 }}>
                {D.previewTaxable}
              </div>
              <div className="num" style={{ fontSize: 16, fontWeight: 600 }}>
                {fmtJD(taxableIncome)}
              </div>
            </div>

            <div
              className="card card-pad"
              style={{
                padding: 12,
                background:
                  refundDue > 0
                    ? "var(--green-tint)"
                    : "var(--paper-alt, #f9fafb)",
                border: "none",
              }}
            >
              <div className="t-eyebrow" style={{ fontSize: 10, marginBottom: 4 }}>
                {refundDue > 0 ? D.previewRefund : D.previewNetDue}
              </div>
              <div
                className="num"
                style={{
                  fontSize: 16,
                  fontWeight: 600,
                  color: refundDue > 0 ? "var(--positive)" : "var(--ink)",
                }}
              >
                {fmtJD(refundDue > 0 ? refundDue : netTaxDue)}
              </div>
            </div>
          </div>

          {/* Navigation Action Links */}
          <div
            className="row"
            style={{
              gap: 12,
              flexWrap: "wrap",
              justifyContent: "flex-end",
              borderTop: "1px solid var(--line)",
              paddingTop: 14,
            }}
          >
            <Link to="/files">
              <Button variant="ghost" size="sm" icon="folder">
                {D.manageDocsCta}
              </Button>
            </Link>
            <Link to="/advisor">
              <Button variant="ghost" size="sm" icon="chart">
                {D.runAdvisorCta}
              </Button>
            </Link>
            <Link to="/settings">
              <Button variant="primary" size="sm" iconRight="arrow">
                {D.editProfileCta}
              </Button>
            </Link>
          </div>
        </>
      )}
    </div>
  );
}
