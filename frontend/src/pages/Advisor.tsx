import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useTaxProfile } from "../contexts/hooks";
import { useAdvisor } from "../contexts/hooks";
import { createIncomeSource } from "../services/api";
import { TaxProfileManager } from "../components/tax/TaxProfileManager";
import AnalysisStepper from "../components/advisor/AnalysisStepper";
import { Icon, Button } from "../components/brand";
import type {
  AdvisorActionStep,
  AdvisorDeductionOpportunity,
  AdvisorLang,
  AdvisorReport,
  AdvisorRiskFlag,
  AdvisorScenario,
  IncomeType,
  TaxCalculationResult,
  TaxProfile,
} from "../types/api";

interface Strings {
  title: string;
  setupHeader: string;
  setupHelp: string;
  marital: string;
  single: string;
  married: string;
  dependents: string;
  continue: string;
  run: string;
  rerun: string;
  running: string;
  profileChip: (year: number, marital: string, deps: number) => string;
  baseline: string;
  scenarios: string;
  opportunities: string;
  risks: string;
  plan: string;
  narrativeDeductions: string;
  narrativeRisk: string;
  narrativePlan: string;
  grossIncome: string;
  taxableIncome: string;
  exemptions: string;
  expenseExemption: string;
  withheld: string;
  netDue: string;
  effective: string;
  marginal: string;
  missingHeader: string;
  missingHelp: string;
  incomeType: string;
  incomeAmount: string;
  employer: string;
  addAndRun: string;
  retry: string;
  errorMsg: string;
  softErrors: string;
  delta: string;
  priority: string;
  citation: string;
  estimatedSavings: string;
  none: string;
  salary: string;
  freelance: string;
  rental: string;
  investment: string;
}

const T: Record<AdvisorLang, Strings> = {
  ar: {
    title: "المستشار الضريبي الاستراتيجي",
    setupHeader: "إعداد ملفك الضريبي",
    setupHelp: "نحتاج معلومتين قبل بدء التحليل.",
    marital: "الحالة الاجتماعية",
    single: "أعزب/عزباء",
    married: "متزوج/ة",
    dependents: "عدد المعالين",
    continue: "متابعة",
    run: "تشغيل التحليل الاستراتيجي",
    rerun: "إعادة التشغيل",
    running: "يجري تشغيل التحليل بمراحله الست... قد يستغرق ~20 ثانية.",
    profileChip: (y: number, m: string, d: number) =>
      `السنة ${y} · ${m === "married" ? "متزوج/ة" : "أعزب/عزباء"} · ${d} معال`,
    baseline: "الضريبة الأساسية",
    scenarios: "سيناريوهات بديلة",
    opportunities: "فرص الخصومات",
    risks: "مؤشرات المخاطر",
    plan: "خطة العمل",
    narrativeDeductions: "ملخص الخصومات",
    narrativeRisk: "ملخص المخاطر",
    narrativePlan: "ملخص الخطة",
    grossIncome: "الدخل الإجمالي",
    taxableIncome: "الدخل الخاضع",
    exemptions: "الإعفاءات",
    expenseExemption: "المصاريف المؤهلة",
    withheld: "الضريبة المقتطعة",
    netDue: "الصافي المستحق",
    effective: "المعدل الفعلي",
    marginal: "أعلى شريحة",
    missingHeader: "الملف غير مكتمل",
    missingHelp: "أضف مصدر دخل واحدًا على الأقل للمتابعة.",
    incomeType: "نوع الدخل",
    incomeAmount: "المبلغ السنوي (دينار)",
    employer: "جهة العمل (اختياري)",
    addAndRun: "إضافة وإعادة التشغيل",
    retry: "إعادة المحاولة",
    errorMsg: "تعذّر تشغيل المستشار. حاول مرة أخرى.",
    softErrors: "تنبيهات: بعض الأقسام واجهت أخطاء.",
    delta: "الفرق",
    priority: "الأولوية",
    citation: "المرجع",
    estimatedSavings: "وفر متوقع",
    none: "—",
    salary: "راتب",
    freelance: "أعمال حرة",
    rental: "إيجار",
    investment: "استثمار",
  },
  en: {
    title: "Strategic Tax Advisor",
    setupHeader: "Set up your tax profile",
    setupHelp: "Two quick details before we run the analysis.",
    marital: "Marital status",
    single: "Single",
    married: "Married",
    dependents: "Number of dependents",
    continue: "Continue",
    run: "Run strategic analysis",
    rerun: "Re-run",
    running: "Running the six-node pipeline... ~20 seconds.",
    profileChip: (y: number, m: string, d: number) =>
      `${y} · ${m === "married" ? "Married" : "Single"} · ${d} dep.`,
    baseline: "Baseline tax",
    scenarios: "Alternative scenarios",
    opportunities: "Deduction opportunities",
    risks: "Risk flags",
    plan: "Action plan",
    narrativeDeductions: "Deductions summary",
    narrativeRisk: "Risk summary",
    narrativePlan: "Plan summary",
    grossIncome: "Gross income",
    taxableIncome: "Taxable income",
    exemptions: "Exemptions",
    expenseExemption: "Eligible expenses",
    withheld: "Tax withheld",
    netDue: "Net due",
    effective: "Effective rate",
    marginal: "Top bracket",
    missingHeader: "Profile incomplete",
    missingHelp: "Add at least one income source to continue.",
    incomeType: "Income type",
    incomeAmount: "Annual amount (JD)",
    employer: "Employer (optional)",
    addAndRun: "Add and re-run",
    retry: "Retry",
    errorMsg: "The advisor could not run. Please try again.",
    softErrors: "Note: some sections had errors.",
    delta: "Δ",
    priority: "Priority",
    citation: "Article",
    estimatedSavings: "Est. savings",
    none: "—",
    salary: "Salary",
    freelance: "Freelance",
    rental: "Rental",
    investment: "Investment",
  },
};

function fmtJD(n: number, lang: AdvisorLang): string {
  const locale = lang === "ar" ? "ar-JO" : "en-US";
  return new Intl.NumberFormat(locale, { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(n);
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

const sectionTitle: CSSProperties = {
  fontSize: 12,
  fontWeight: 600,
  letterSpacing: ".12em",
  textTransform: "uppercase",
  color: "var(--green)",
  marginBottom: 16,
};

export default function Advisor() {
  const { profile, loading: profileLoading, refreshTaxProfile, version: taxProfileVersion } = useTaxProfile();
  const { phase, report, errorMsg, reportProfileVersion, lang, setPhase, setLang, setErrorMsg, runAnalysis } = useAdvisor();
  const [editOpen, setEditOpen] = useState(false);
  const planRef = useRef<HTMLDivElement>(null);
  const incomeFormRef = useRef<HTMLDivElement>(null);

  const [incomeType, setIncomeType] = useState<IncomeType>("salary");
  const [incomeAmount, setIncomeAmount] = useState<string>("");
  const [employer, setEmployer] = useState<string>("");
  const [savingIncome, setSavingIncome] = useState(false);

  const t = T[lang];

  useEffect(() => {
    if (profileLoading && !profile) return;
    if (!profile) {
      setPhase("bootstrap");
      return;
    }
    setPhase((current) =>
      current === "loading" || current === "bootstrap" || current === "error" ? "ready" : current,
    );
  }, [profileLoading, profile, setPhase]);

  async function handleRun(options?: { profile?: TaxProfile | null; lang?: AdvisorLang; version?: number }) {
    const targetProfile = options?.profile ?? profile;
    if (!targetProfile) return;
    const runLang = options?.lang ?? lang;
    const version = options?.version ?? taxProfileVersion;
    await runAnalysis(targetProfile, runLang, version, T[runLang].errorMsg);
  }

  async function handleAddIncome(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    const parsed = parseFloat(incomeAmount);
    if (!Number.isFinite(parsed) || parsed <= 0) return;
    setSavingIncome(true);
    try {
      await createIncomeSource({
        tax_profile_id: profile.id,
        type: incomeType,
        amount: parsed,
        employer_name: employer.trim() || null,
      }, profile.version);
      setIncomeAmount("");
      setEmployer("");
      const snapshot = await refreshTaxProfile();
      await handleRun({ profile: snapshot.profile, version: snapshot.version });
    } catch {
      setErrorMsg(t.errorMsg);
      setPhase("error");
    } finally {
      setSavingIncome(false);
    }
  }

  function toggleLang() {
    const next: AdvisorLang = lang === "ar" ? "en" : "ar";
    setLang(next);
    if (phase === "report" && profile) void handleRun({ lang: next });
  }

  const dir = lang === "ar" ? "rtl" : "ltr";
  const incomplete = report?.status === "incomplete";
  const reportIsStale =
    phase === "report" && report !== null && reportProfileVersion !== null && reportProfileVersion !== taxProfileVersion;

  return (
    <div dir={dir} className="wrap wrap-app" style={{ maxWidth: 1040, paddingBlock: "32px 64px" }}>
      <Header
        t={t}
        lang={lang}
        profile={profile}
        onToggleLang={toggleLang}
        onRerun={() => handleRun()}
        onEdit={() => setEditOpen((open) => !open)}
        canRerun={phase === "report" || phase === "ready"}
      />

      <div className="stack" style={{ ["--gap"]: "20px", marginTop: 24 } as CSSProperties}>
        {phase === "loading" && <Loading label="…" />}

        {phase === "bootstrap" && (
          <div className="card card-pad">
            <h2 className="t-h3" style={{ marginBottom: 4 }}>
              {t.setupHeader}
            </h2>
            <p className="t-small" style={{ marginBottom: 18 }}>
              {t.setupHelp}
            </p>
            <TaxProfileManager
              compact
              lang={lang}
              onProfileChange={(next) => {
                if (!next) return;
                setPhase("ready");
              }}
            />
          </div>
        )}

        {profile && editOpen && phase !== "bootstrap" && (
          <div className="card card-pad">
            <TaxProfileManager
              compact
              lang={lang}
              onSaved={async (snapshot) => {
                if ((phase === "ready" || phase === "report") && snapshot.profile) {
                  await handleRun({ profile: snapshot.profile, version: snapshot.version });
                }
              }}
            />
          </div>
        )}

        {phase === "ready" && <ReadyCard t={t} onRun={() => handleRun()} />}
        {phase === "error" && <ErrorCard message={errorMsg ?? t.errorMsg} onRetry={() => handleRun()} retryLabel={t.retry} />}

        {(phase === "running" || (phase === "report" && report)) && (
          <AnalysisStepper
            report={phase === "report" ? report : null}
            lang={lang}
            live={phase === "running"}
            onUpload={() => incomeFormRef.current?.scrollIntoView({ behavior: "smooth", block: "center" })}
            onViewPlan={() => planRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
          />
        )}

        {phase === "report" && report && (
          <>
            {reportIsStale && (
              <div className="card card-pad row-between" style={{ borderColor: "var(--green)", gap: 12 }}>
                <span className="t-small" style={{ color: "var(--ink)" }}>
                  {lang === "ar" ? "تغيّر الملف الضريبي. أعد التشغيل لاستخدام القيم المحدّثة." : "Tax profile changed. Re-run to use updated values."}
                </span>
                <Button variant="primary" size="sm" onClick={() => handleRun()}>
                  {t.rerun}
                </Button>
              </div>
            )}

            {report.errors.length > 0 && (
              <div className="card card-pad" style={{ borderColor: "var(--attention)", color: "var(--attention)" }}>
                {t.softErrors} {report.errors.join(", ")}
              </div>
            )}

            {incomplete ? (
              <div ref={incomeFormRef}>
                <IncompleteCard
                  t={t}
                  missingFields={report.missing_fields}
                  incomeType={incomeType}
                  incomeAmount={incomeAmount}
                  employer={employer}
                  saving={savingIncome}
                  onType={setIncomeType}
                  onAmount={setIncomeAmount}
                  onEmployer={setEmployer}
                  onSubmit={handleAddIncome}
                />
              </div>
            ) : (
              <>
                {report.baseline && <BaselineCard t={t} lang={lang} baseline={report.baseline} />}
                {report.scenarios.length > 0 && <ScenarioComparison t={t} lang={lang} scenarios={report.scenarios} />}
                {report.deduction_opportunities.length > 0 && <OpportunityList t={t} lang={lang} items={report.deduction_opportunities} />}
                {report.risk_flags.length > 0 && <RiskFlagList t={t} items={report.risk_flags} />}
                {report.action_plan.length > 0 && (
                  <div ref={planRef}>
                    <ActionPlanList t={t} items={report.action_plan} />
                  </div>
                )}
                <Narratives t={t} narratives={report.narratives} />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Header({
  t,
  lang,
  profile,
  onToggleLang,
  onRerun,
  onEdit,
  canRerun,
}: {
  t: Strings;
  lang: AdvisorLang;
  profile: TaxProfile | null;
  onToggleLang: () => void;
  onRerun: () => void;
  onEdit: () => void;
  canRerun: boolean;
}) {
  return (
    <div className="row-between" style={{ gap: 12, flexWrap: "wrap" }}>
      <h1 className="display t-h1">{t.title}</h1>
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        {profile && <span className="pill">{t.profileChip(profile.tax_year, profile.marital_status, profile.num_dependents)}</span>}
        <Button variant="ghost" size="sm" onClick={onToggleLang}>
          {lang === "ar" ? "EN" : "ع"}
        </Button>
        {profile && (
          <Button variant="ghost" size="sm" onClick={onEdit} icon="pencil">
            {lang === "ar" ? "تعديل" : "Edit"}
          </Button>
        )}
        {canRerun && (
          <Button variant="primary" size="sm" icon="refresh" onClick={onRerun}>
            {t.rerun}
          </Button>
        )}
      </div>
    </div>
  );
}

function Loading({ label }: { label: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16, padding: "80px 0", color: "var(--ink-soft)" }}>
      <div style={{ width: 40, height: 40, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)", animation: "spin 1s linear infinite" }} />
      <p className="t-small center" style={{ maxWidth: 420 }}>
        {label}
      </p>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );
}

function ErrorCard({ message, onRetry, retryLabel }: { message: string; onRetry: () => void; retryLabel: string }) {
  return (
    <div className="card card-pad center" style={{ borderColor: "var(--danger)" }}>
      <p style={{ marginBottom: 16 }}>{message}</p>
      <Button variant="primary" onClick={onRetry}>
        {retryLabel}
      </Button>
    </div>
  );
}

function ReadyCard({ t, onRun }: { t: Strings; onRun: () => void }) {
  return (
    <div className="card card-pad center" style={{ paddingBlock: 48 }}>
      <div style={{ width: 64, height: 64, margin: "0 auto 16px", borderRadius: 18, background: "var(--green-tint)", display: "grid", placeItems: "center" }}>
        <Icon name="chart" size={28} color="var(--green)" />
      </div>
      <p className="t-body" style={{ maxWidth: 440, marginInline: "auto", marginBottom: 24 }}>
        {t.running}
      </p>
      <Button variant="primary" size="lg" iconRight="arrow" onClick={onRun}>
        {t.run}
      </Button>
    </div>
  );
}

function BaselineCard({ t, lang, baseline }: { t: Strings; lang: AdvisorLang; baseline: TaxCalculationResult }) {
  return (
    <section className="card card-pad">
      <h2 style={sectionTitle}>{t.baseline}</h2>
      <div className="num" style={{ fontSize: 40, fontWeight: 600, marginBottom: 4 }}>
        {fmtJD(baseline.tax_liability, lang)} <span style={{ fontSize: 16, color: "var(--ink-soft)", fontWeight: 500 }}>JD</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginTop: 22 }} className="max-md:!grid-cols-2">
        <Stat label={t.grossIncome} value={`${fmtJD(baseline.gross_income, lang)} JD`} />
        <Stat label={t.taxableIncome} value={`${fmtJD(baseline.taxable_income, lang)} JD`} />
        <Stat label={t.exemptions} value={`${fmtJD(baseline.total_exemptions, lang)} JD`} />
        <Stat label={t.expenseExemption} value={`${fmtJD(baseline.expense_exemption, lang)} JD`} />
        <Stat label={t.withheld} value={`${fmtJD(baseline.total_tax_withheld, lang)} JD`} />
        <Stat label={t.netDue} value={`${fmtJD(baseline.net_tax_due, lang)} JD`} />
        <Stat label={t.effective} value={fmtPct(baseline.effective_rate)} />
        <Stat label={t.marginal} value={fmtPct(baseline.marginal_rate)} />
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10, marginBottom: 4 }}>
        {label}
      </div>
      <div className="num" style={{ fontSize: 18, fontWeight: 600 }}>
        {value}
      </div>
    </div>
  );
}

function ScenarioComparison({ t, lang, scenarios }: { t: Strings; lang: AdvisorLang; scenarios: AdvisorScenario[] }) {
  const cheapest = useMemo(
    () => scenarios.reduce((min, s) => (s.tax_liability < min.tax_liability ? s : min), scenarios[0]),
    [scenarios],
  );
  return (
    <section>
      <h2 style={{ ...sectionTitle, paddingInline: 4 }}>{t.scenarios}</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 16 }} className="max-md:!grid-cols-1">
        {scenarios.map((s, i) => {
          const isCheapest = s === cheapest;
          const positive = s.delta_vs_baseline > 0;
          return (
            <div key={i} className="card card-pad" style={{ borderColor: isCheapest ? "var(--green)" : "var(--line)", boxShadow: isCheapest ? "var(--shadow-glow)" : "var(--shadow-sm)" }}>
              <div className="t-body" style={{ color: "var(--ink)", fontWeight: 600, marginBottom: 10 }}>
                {s.label}
              </div>
              <div className="num" style={{ fontSize: 26, fontWeight: 600, marginBottom: 6 }}>
                {fmtJD(s.tax_liability, lang)} <span style={{ fontSize: 12, color: "var(--ink-soft)" }}>JD</span>
              </div>
              <div className="t-small num" style={{ fontWeight: 600, color: s.delta_vs_baseline === 0 ? "var(--ink-faint)" : positive ? "var(--danger)" : "var(--positive)" }}>
                {t.delta} {positive ? "+" : ""}
                {fmtJD(s.delta_vs_baseline, lang)} JD
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function OpportunityList({ t, lang, items }: { t: Strings; lang: AdvisorLang; items: AdvisorDeductionOpportunity[] }) {
  return (
    <section className="card card-pad">
      <h2 style={sectionTitle}>{t.opportunities}</h2>
      <ul className="stack" style={{ ["--gap"]: "16px", listStyle: "none", margin: 0, padding: 0 } as CSSProperties}>
        {items.map((op, i) => (
          <li key={i} style={{ borderBottom: i < items.length - 1 ? "1px solid var(--line)" : "none", paddingBottom: i < items.length - 1 ? 16 : 0 }}>
            <div className="row-between" style={{ gap: 12, marginBottom: 4 }}>
              <span className="chip chip-green" style={{ textTransform: "uppercase" }}>
                {op.category}
              </span>
              {op.estimated_savings != null && (
                <span className="t-small num" style={{ fontWeight: 600, color: "var(--positive)" }}>
                  {t.estimatedSavings}: {fmtJD(op.estimated_savings, lang)} JD
                </span>
              )}
            </div>
            <p className="t-body" style={{ color: "var(--ink)", marginTop: 8 }}>
              {op.description}
            </p>
            {op.citation && (
              <p className="t-small faint" style={{ marginTop: 8 }}>
                {t.citation}: {op.citation}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function RiskFlagList({ t, items }: { t: Strings; items: AdvisorRiskFlag[] }) {
  const sev: Record<AdvisorRiskFlag["severity"], { bg: string; fg: string }> = {
    low: { bg: "var(--green-tint)", fg: "var(--green)" },
    medium: { bg: "var(--gold-tint)", fg: "var(--attention)" },
    high: { bg: "var(--clay-tint)", fg: "var(--danger)" },
  };
  return (
    <section className="card card-pad">
      <h2 style={sectionTitle}>{t.risks}</h2>
      <ul className="stack" style={{ ["--gap"]: "12px", listStyle: "none", margin: 0, padding: 0 } as CSSProperties}>
        {items.map((f, i) => (
          <li key={i} style={{ borderRadius: 12, padding: "12px 16px", background: sev[f.severity].bg }}>
            <div className="t-eyebrow" style={{ color: sev[f.severity].fg, fontSize: 10, marginBottom: 4 }}>
              {f.severity}
            </div>
            <p className="t-body" style={{ color: "var(--ink)" }}>
              {f.issue}
            </p>
            {f.suggestion && (
              <p className="t-small" style={{ marginTop: 6 }}>
                → {f.suggestion}
              </p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function ActionPlanList({ t, items }: { t: Strings; items: AdvisorActionStep[] }) {
  const sorted = useMemo(() => [...items].sort((a, b) => a.priority - b.priority), [items]);
  return (
    <section className="card card-pad">
      <h2 style={sectionTitle}>{t.plan}</h2>
      <ol className="stack" style={{ ["--gap"]: "14px", listStyle: "none", margin: 0, padding: 0 } as CSSProperties}>
        {sorted.map((step, i) => (
          <li key={i} className="row" style={{ gap: 14, alignItems: "flex-start" }}>
            <span style={{ flex: "none", width: 32, height: 32, borderRadius: 9, background: "var(--green-tint)", color: "var(--green)", fontWeight: 700, display: "grid", placeItems: "center" }} className="num">
              {step.priority}
            </span>
            <div>
              <p className="t-body" style={{ color: "var(--ink)", fontWeight: 600 }}>
                {step.action}
              </p>
              {step.description && (
                <p className="t-small" style={{ marginTop: 2 }}>
                  {step.description}
                </p>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Narratives({ t, narratives }: { t: Strings; narratives: AdvisorReport["narratives"] }) {
  const items: Array<[string, string]> = [
    [t.narrativeDeductions, narratives.deductions],
    [t.narrativeRisk, narratives.risk],
    [t.narrativePlan, narratives.plan],
  ];
  const present = items.filter(([, body]) => body && body.trim().length > 0);
  if (present.length === 0) return null;
  return (
    <section className="stack" style={{ ["--gap"]: "10px" } as CSSProperties}>
      {present.map(([title, body]) => (
        <details key={title} className="card" style={{ padding: "14px 20px" }}>
          <summary className="row-between" style={{ cursor: "pointer", listStyle: "none", fontWeight: 600, color: "var(--ink)" }}>
            <span>{title}</span>
            <Icon name="chevron" size={16} color="var(--ink-faint)" style={{ transform: "rotate(90deg)" }} />
          </summary>
          <p className="t-body" style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>
            {body}
          </p>
        </details>
      ))}
    </section>
  );
}

function IncompleteCard({
  t,
  missingFields,
  incomeType,
  incomeAmount,
  employer,
  saving,
  onType,
  onAmount,
  onEmployer,
  onSubmit,
}: {
  t: Strings;
  missingFields: string[];
  incomeType: IncomeType;
  incomeAmount: string;
  employer: string;
  saving: boolean;
  onType: (t: IncomeType) => void;
  onAmount: (s: string) => void;
  onEmployer: (s: string) => void;
  onSubmit: (e: React.FormEvent) => void;
}) {
  const incomeLabels: Record<IncomeType, string> = {
    salary: t.salary,
    freelance: t.freelance,
    rental: t.rental,
    investment: t.investment,
  };
  return (
    <form onSubmit={onSubmit} className="card card-pad" style={{ borderColor: "var(--attention)", display: "flex", flexDirection: "column", gap: 20 }}>
      <div>
        <h2 className="t-h3" style={{ color: "var(--attention)", marginBottom: 4 }}>
          {t.missingHeader}
        </h2>
        <p className="t-small">
          {t.missingHelp} <span className="faint">({missingFields.join(", ")})</span>
        </p>
      </div>

      <div className="field">
        <label className="field-label">{t.incomeType}</label>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 8 }}>
          {(["salary", "freelance", "rental", "investment"] as IncomeType[]).map((k) => {
            const active = incomeType === k;
            return (
              <button
                key={k}
                type="button"
                onClick={() => onType(k)}
                style={{
                  padding: "9px 0",
                  borderRadius: 9,
                  fontSize: 13,
                  fontWeight: 600,
                  border: "1px solid " + (active ? "var(--green)" : "var(--line-strong)"),
                  background: active ? "var(--green-tint)" : "var(--paper)",
                  color: active ? "var(--green)" : "var(--ink-soft)",
                }}
              >
                {incomeLabels[k]}
              </button>
            );
          })}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }} className="max-md:!grid-cols-1">
        <div className="field">
          <label className="field-label">{t.incomeAmount}</label>
          <input type="number" min={0} step={100} className="input" value={incomeAmount} onChange={(e) => onAmount(e.target.value)} required />
        </div>
        <div className="field">
          <label className="field-label">{t.employer}</label>
          <input type="text" className="input" value={employer} onChange={(e) => onEmployer(e.target.value)} />
        </div>
      </div>

      <Button type="submit" variant="primary" disabled={saving || !incomeAmount} style={{ width: "100%" }}>
        {saving ? "…" : t.addAndRun}
      </Button>
    </form>
  );
}
