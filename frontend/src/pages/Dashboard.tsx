import { useEffect, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../contexts/hooks";
import { useTaxProfile } from "../contexts/hooks";
import { useLang } from "../contexts/hooks";
import { api } from "../services/api";
import type { NotificationItem } from "../types/api";
import { Icon, Button, Tatreez, type IconName } from "../components/brand";
import { ProfileCompletionGuide, QuotaUsageIndicator, TaxYearSummary } from "../components/guidance";

type DashboardData = {
  documentCount: number;
  pendingDocCount: number;
  notifications: NotificationItem[];
};

function fmtJD(n: number, locale = "en-US"): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n);
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="wrap wrap-app" style={{ paddingBlock: "40px 64px" }}>
      {children}
    </div>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const { profile, calculation: calc, loading: taxLoading, error: taxError } = useTaxProfile();
  const { t, fill } = useLang();
  const D = t.dashboard;
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setErrorMsg(null);
        const [documentsResp, notifsResp] = await Promise.all([
          api.get<{ id: string; processing_status?: string }[]>("/documents/"),
          api.get<NotificationItem[]>("/notifications/"),
        ]);
        if (cancelled) return;
        const pendingCount = documentsResp.data.filter(
          (d) => d.processing_status === "pending"
        ).length;
        setData({
          documentCount: documentsResp.data.length,
          pendingDocCount: pendingCount,
          notifications: notifsResp.data,
        });
      } catch {
        if (!cancelled) setErrorMsg(t.common.error);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading || (taxLoading && !profile)) {
    return (
      <PageShell>
        <div style={{ display: "grid", placeItems: "center", paddingBlock: 120 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 999,
              border: "3px solid var(--green-tint2)",
              borderTopColor: "var(--green)",
              animation: "spin 1s linear infinite",
            }}
          />
          <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
        </div>
      </PageShell>
    );
  }

  const visibleError = errorMsg ?? taxError;
  if (visibleError) {
    return (
      <PageShell>
        <div className="card card-pad center" style={{ borderColor: "var(--danger)", maxWidth: 640, marginInline: "auto" }}>
          <p style={{ color: "var(--danger)" }}>{visibleError}</p>
        </div>
      </PageShell>
    );
  }

  if (!profile) {
    return (
      <PageShell>
        <div style={{ marginBottom: 24 }}>
          <h1 className="display t-h1" style={{ marginBottom: 6 }}>
            {D.greeting} {user?.name?.split(" ")[0] ?? ""}
          </h1>
        </div>
        <ProfileCompletionGuide
          documentCount={data?.documentCount ?? 0}
          pendingDocCount={data?.pendingDocCount ?? 0}
        />
        <div className="card card-pad center" style={{ maxWidth: 560, marginInline: "auto", paddingBlock: 48 }}>
          <div style={{ width: 56, height: 56, borderRadius: 16, background: "var(--green-tint)", display: "grid", placeItems: "center", margin: "0 auto 18px" }}>
            <Icon name="chart" size={26} color="var(--green)" />
          </div>
          <h1 className="display t-h2" style={{ marginBottom: 8 }}>
            {D.noProfileTitle}
          </h1>
          <p className="t-body" style={{ marginBottom: 22 }}>
            {D.noProfileSub}
          </p>
          <Link to="/settings">
            <Button variant="primary" iconRight="arrow">
              {t.guidance.step1Cta}
            </Button>
          </Link>
        </div>
      </PageShell>
    );
  }

  const maritalLabel = profile.marital_status === "married" ? t.settings.married : t.settings.single;

  if (!calc) {
    return (
      <PageShell>
        <div style={{ marginBottom: 24 }}>
          <h1 className="display t-h1" style={{ marginBottom: 6 }}>
            {D.greeting} {user?.name?.split(" ")[0] ?? ""}
          </h1>
          <p className="t-body">
            {fill(D.sub, {
              year: profile.tax_year,
              marital: maritalLabel,
              deps: profile.num_dependents,
            })}
          </p>
        </div>
        <ProfileCompletionGuide
          documentCount={data?.documentCount ?? 0}
          pendingDocCount={data?.pendingDocCount ?? 0}
        />
        <TaxYearSummary />
        <div className="card card-pad center" style={{ maxWidth: 600, marginInline: "auto", paddingBlock: 48, borderColor: "var(--attention)" }}>
          <div style={{ width: 56, height: 56, borderRadius: 16, background: "var(--gold-tint)", display: "grid", placeItems: "center", margin: "0 auto 18px" }}>
            <Icon name="bolt" size={26} color="var(--attention)" />
          </div>
          <h1 className="display t-h2" style={{ marginBottom: 8 }}>
            {D.noCalcTitle}
          </h1>
          <p className="t-body" style={{ marginBottom: 22 }}>
            {D.noCalcSub}
          </p>
          <div className="row" style={{ gap: 12, justifyContent: "center" }}>
            <Link to="/settings">
              <Button variant="primary">{t.settings.taxTitle}</Button>
            </Link>
            <Link to="/advisor">
              <Button variant="ghost">{D.navAdvisor}</Button>
            </Link>
          </div>
        </div>
      </PageShell>
    );
  }

  const {
    tax_liability: taxLiability,
    net_tax_due: netTaxDue,
    refund_due: refundDue,
    gross_income: grossIncome,
    effective_rate: effectiveRate,
    total_exemptions: totalExemptions,
    expense_exemption: expenseExemption,
    total_tax_withheld: totalTaxWithheld,
  } = calc;

  const isRefund = refundDue > 0;
  const isAr = t.dir === "rtl";
  const numLocale = isAr ? "ar-JO" : "en-US";
  const curr = isAr ? "د.أ" : "JD";

  const stats: { label: string; value: string }[] = [
    { label: D.stat1, value: `${fmtJD(grossIncome, numLocale)} ${curr}` },
    { label: D.stat2, value: `${fmtJD(totalExemptions, numLocale)} ${curr}` },
    { label: D.stat3, value: `${fmtJD(expenseExemption, numLocale)} ${curr}` },
    { label: D.stat4, value: fmtPct(effectiveRate) },
  ];

  const actions: { to: string; icon: IconName; title: string; desc: string }[] = [
    { to: "/advisor", icon: "chart", title: D.actAdvisorT, desc: D.actAdvisorD },
    { to: "/files", icon: "folder", title: D.actFilesT, desc: D.actFilesD },
  ];

  return (
    <PageShell>
      {/* Greeting */}
      <div style={{ marginBottom: 24 }}>
        <h1 className="display t-h1" style={{ marginBottom: 6 }}>
          {D.greeting} {user?.name?.split(" ")[0] ?? ""}
        </h1>
        <p className="t-body">
          {fill(D.sub, {
            year: profile.tax_year,
            marital: maritalLabel,
            deps: profile.num_dependents,
          })}
        </p>
      </div>

      {/* Profile Completion Guidance */}
      <ProfileCompletionGuide
        documentCount={data?.documentCount ?? 0}
        pendingDocCount={data?.pendingDocCount ?? 0}
      />

      {/* Headline number */}
      <div className="card" style={{ position: "relative", overflow: "hidden", padding: 32, marginBottom: 22 }}>
        <Tatreez scale={32} opacity={0.35} fade />
        <div style={{ position: "relative" }}>
          <div className="t-eyebrow" style={{ marginBottom: 10 }}>
            {fill(isRefund ? D.headlineRefundLabel : D.headlineDueLabel, { year: profile.tax_year })}
          </div>
          <div
            className="num"
            style={{ fontSize: 54, fontWeight: 600, lineHeight: 1, color: isRefund ? "var(--positive)" : "var(--ink)" }}
          >
            {fmtJD(isRefund ? refundDue : netTaxDue, numLocale)}{" "}
            <span style={{ fontSize: 20, color: "var(--ink-soft)", fontWeight: 500 }}>{curr}</span>
          </div>
          <div className="t-small" style={{ marginTop: 12 }}>
            {fill(D.headlineFoot, { liab: fmtJD(taxLiability, numLocale), withheld: fmtJD(totalTaxWithheld, numLocale) })}
          </div>
          <div style={{ marginTop: 20 }}>
            <Link to="/advisor">
              <Button variant="primary" iconRight="arrow">
                {D.runAnalysis}
              </Button>
            </Link>
          </div>
        </div>
      </div>

      {/* Quota & Legal Exemption Allowances */}
      <QuotaUsageIndicator />

      {/* Server-backed Tax Year Summary */}
      <TaxYearSummary />

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 22 }} className="max-md:!grid-cols-2">
        {stats.map((s) => (
          <div key={s.label} className="card card-pad" style={{ padding: 18 }}>
            <div className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10.5, marginBottom: 6 }}>
              {s.label}
            </div>
            <div className="num" style={{ fontSize: 22, fontWeight: 600 }}>
              {s.value}
            </div>
          </div>
        ))}
      </div>

      {/* Action panels */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 22 }} className="max-md:!grid-cols-1">
        {actions.map((a) => (
          <Link key={a.to} to={a.to} className="card card-hover card-pad" style={{ display: "block" }}>
            <div className="row" style={{ gap: 14, alignItems: "flex-start" }}>
              <div style={{ width: 44, height: 44, borderRadius: 12, background: "var(--green-tint)", display: "grid", placeItems: "center", flex: "none" }}>
                <Icon name={a.icon} size={20} color="var(--green)" />
              </div>
              <div>
                <h3 className="t-h3" style={{ fontSize: 17, marginBottom: 5 }}>
                  {a.title}
                </h3>
                <p className="t-small">{a.desc}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* Notifications preview */}
      {data?.notifications && data.notifications.length > 0 && (
        <div className="card card-pad">
          <div className="row-between" style={{ marginBottom: 14 }}>
            <h3 className="t-eyebrow">{D.attention}</h3>
            <Link to="/notifications" className="green t-small" style={{ fontWeight: 600 }}>
              {D.seeAll} →
            </Link>
          </div>
          <ul className="stack" style={{ ["--gap"]: "12px", listStyle: "none", margin: 0, padding: 0 } as CSSProperties}>
            {data.notifications.slice(0, 3).map((n) => (
              <li key={n.id} className="row" style={{ gap: 12, alignItems: "flex-start" }}>
                <span
                  style={{
                    marginTop: 6,
                    width: 8,
                    height: 8,
                    borderRadius: 999,
                    flex: "none",
                    background:
                      n.severity === "warning"
                        ? "var(--attention)"
                        : n.severity === "action"
                          ? "var(--green)"
                          : "var(--ink-faint)",
                  }}
                />
                <span className="t-body" style={{ color: "var(--ink)" }}>
                  {n.message}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </PageShell>
  );
}
