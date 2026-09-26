/* ============================================================
   BAYYAN — Strategic Analysis pipeline model + run clock.

   Recreates the design-handoff "run-model.js" in TypeScript, but the
   node *content* is built from the real AdvisorReport instead of mock
   data. The 6 nodes mirror the backend LangGraph graph 1:1:
     gather → completeness (router) → deductions → scenarios (parallel)
     → risk (gate) → plan.

   The backend returns ONE AdvisorReport payload (it does not stream
   node-by-node), so `useStepperRun` is a presentation clock: it animates
   the rail while a run is in flight (`live`) and settles onto the real
   result when the report arrives. Honors prefers-reduced-motion.
   ============================================================ */
import { useCallback, useEffect, useRef, useState } from "react";
import type { IconName } from "../brand";
import type { AdvisorLang, AdvisorReport } from "../../types/api";

export type NodeKind = "step" | "decision" | "parallel" | "gate";

export interface StepperLane {
  name: string;
  tax: string;
  delta: number;
  best: boolean;
}

export interface StepperBranch {
  title: string;
  line: string;
  cta: string;
}

export interface StepperNode {
  id: string;
  icon: IconName;
  kind: NodeKind;
  dur: number;
  label: string;
  tool: string;
  kindTag: string;
  verb: string;
  summary: string;
  detail?: [string, string][];
  lanes?: StepperLane[];
  branch?: StepperBranch;
  gatePass?: boolean;
  gateText?: string;
}

/* ---- localized static metadata for the 6 nodes (constant) ---- */
interface NodeMeta {
  id: string;
  icon: IconName;
  kind: NodeKind;
  dur: number;
  label: { ar: string; en: string };
  tool: { ar: string; en: string };
  verb: { ar: string; en: string };
}

const NODE_META: NodeMeta[] = [
  {
    id: "gather",
    icon: "folder",
    kind: "step",
    dur: 1250,
    label: { ar: "تجميع", en: "Gather" },
    tool: { ar: "قراءة ضوئية", en: "Vision OCR" },
    verb: { ar: "قراءة الملف والمستندات", en: "Reading profile & documents" },
  },
  {
    id: "completeness",
    icon: "search",
    kind: "decision",
    dur: 1350,
    label: { ar: "الاكتمال", en: "Completeness" },
    tool: { ar: "موجِّه", en: "Router" },
    verb: { ar: "البحث عن سجلات ناقصة", en: "Checking for missing records" },
  },
  {
    id: "deductions",
    icon: "receipt",
    kind: "step",
    dur: 1250,
    label: { ar: "الخصومات", en: "Deductions" },
    tool: { ar: "القانون ٣٤/٢٠١٤", en: "Law 34/2014" },
    verb: { ar: "مطابقة الخصومات مع القانون ٣٤/٢٠١٤", en: "Matching receipts to Law 34/2014" },
  },
  {
    id: "scenarios",
    icon: "chart",
    kind: "parallel",
    dur: 1650,
    label: { ar: "السيناريوهات", en: "Scenarios" },
    tool: { ar: "محرّك السيناريوهات", en: "Scenario engine" },
    verb: { ar: "تشغيل الاستراتيجيات بالتوازي", en: "Running strategies in parallel" },
  },
  {
    id: "risk",
    icon: "shield",
    kind: "gate",
    dur: 1150,
    label: { ar: "المخاطر", en: "Risk" },
    tool: { ar: "بوابة", en: "Gate" },
    verb: { ar: "تقييم مخاطر التدقيق", en: "Assessing audit exposure" },
  },
  {
    id: "plan",
    icon: "check",
    kind: "step",
    dur: 1050,
    label: { ar: "الخطة", en: "Plan" },
    tool: { ar: "مُخطِّط", en: "Planner" },
    verb: { ar: "تجهيز خطة العمل", en: "Compiling your action plan" },
  },
];

/** completeness is node index 1; an incomplete run settles after it. */
export const COMPLETENESS_INDEX = 1;
export const NODE_COUNT = NODE_META.length;

/* ---- helpers ---- */
const pick = (v: { ar: string; en: string }, lang: AdvisorLang) => (lang === "ar" ? v.ar : v.en);

export function fmtJD(n: number, lang: AdvisorLang): string {
  const locale = lang === "ar" ? "ar-JO" : "en-US";
  return new Intl.NumberFormat(locale, { minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(
    Math.round(n),
  );
}

const CATEGORY: Record<string, { ar: string; en: string }> = {
  medical: { ar: "نفقات طبية", en: "Medical" },
  education: { ar: "تعليم", en: "Education" },
  rent: { ar: "إيجار", en: "Rent" },
  donations: { ar: "تبرعات", en: "Donations" },
  insurance: { ar: "تأمين", en: "Insurance" },
  pension: { ar: "تقاعد", en: "Pension" },
  housing_interest: { ar: "فوائد قرض سكن", en: "Housing interest" },
  housing_murabaha: { ar: "مرابحة سكن", en: "Housing murabaha" },
};
const catLabel = (c: string, lang: AdvisorLang) =>
  CATEGORY[c] ? pick(CATEGORY[c], lang) : c.replace(/_/g, " ");

const SEVERITY: Record<"low" | "medium" | "high", { ar: string; en: string }> = {
  low: { ar: "منخفض", en: "Low" },
  medium: { ar: "متوسط", en: "Medium" },
  high: { ar: "مرتفع", en: "High" },
};

const MISSING_FIELD: Record<string, { ar: string; en: string }> = {
  marital_status: { ar: "الحالة الاجتماعية", en: "Marital status" },
  residency_status: { ar: "حالة الإقامة", en: "Residency status" },
  num_dependents: { ar: "عدد المعالين", en: "Dependents" },
  income_sources: { ar: "مصدر دخل", en: "Income source" },
};
const fieldLabel = (f: string, lang: AdvisorLang) =>
  MISSING_FIELD[f] ? pick(MISSING_FIELD[f], lang) : f.replace(/_/g, " ");
const listSep = (lang: AdvisorLang) => (lang === "ar" ? "، " : ", ");

/* ---- localized chrome strings for the stepper shell ---- */
export interface StepperStrings {
  eyebrow: string;
  title: string;
  running: string;
  complete: string;
  needsInput: string;
  replay: string;
  reviewHint: string;
  stepOf: (i: number, total: number) => string;
  working: string;
  done: string;
  analysisComplete: string;
  refund: (v: string) => string;
  netDue: (v: string) => string;
  actionsReady: (n: number) => string;
  viewPlan: string;
}

export const STEPPER_T: Record<AdvisorLang, StepperStrings> = {
  ar: {
    eyebrow: "التحليل الاستراتيجي",
    title: "كيف حلّل بيان إقرارك",
    running: "قيد التشغيل",
    complete: "اكتمل",
    needsInput: "بحاجة لإدخالك",
    replay: "إعادة العرض",
    reviewHint: "اضغط أي خطوة بالأعلى لمراجعة ما قامت به",
    stepOf: (i, total) => `الخطوة ${i} من ${total}`,
    working: "جارٍ العمل…",
    done: "تم",
    analysisComplete: "اكتمل التحليل",
    refund: (v) => `استرداد ${v} دينار`,
    netDue: (v) => `مستحق ${v} دينار`,
    actionsReady: (n) => `${n} إجراءات جاهزة`,
    viewPlan: "عرض خطة العمل",
  },
  en: {
    eyebrow: "Strategic analysis",
    title: "How Bayyan ran your return",
    running: "Running",
    complete: "Complete",
    needsInput: "Needs input",
    replay: "Replay",
    reviewHint: "Click any step above to review what it did",
    stepOf: (i, total) => `Step ${i} of ${total}`,
    working: "Working…",
    done: "Done",
    analysisComplete: "Analysis complete",
    refund: (v) => `Refund ${v} JD`,
    netDue: (v) => `Net due ${v} JD`,
    actionsReady: (n) => `${n} actions ready`,
    viewPlan: "View action plan",
  },
};

const kindTag = (kind: NodeKind, tool: string, lang: AdvisorLang) => {
  if (kind === "decision") return pick({ ar: "موجِّه", en: "Router" }, lang);
  if (kind === "parallel") return pick({ ar: "تفرّع ×٣", en: "Parallel ×3" }, lang);
  if (kind === "gate") return pick({ ar: "بوابة", en: "Gate" }, lang);
  return tool;
};

/* ============================================================
   buildNodes — resolve the static node metadata against a real
   AdvisorReport. When `report` is null (a fresh run is in flight),
   only the static chrome is present; result fields fill in on arrival.
   ============================================================ */
export function buildNodes(report: AdvisorReport | null, lang: AdvisorLang): StepperNode[] {
  const L = (ar: string, en: string) => (lang === "ar" ? ar : en);
  const baseline = report?.baseline ?? null;

  return NODE_META.map((m) => {
    const base: StepperNode = {
      id: m.id,
      icon: m.icon,
      kind: m.kind,
      dur: m.dur,
      label: pick(m.label, lang),
      tool: pick(m.tool, lang),
      kindTag: kindTag(m.kind, pick(m.tool, lang), lang),
      verb: pick(m.verb, lang),
      summary: "",
    };
    if (!report) return base;

    switch (m.id) {
      case "gather": {
        const detail: [string, string][] = [];
        if (baseline) {
          detail.push([L("الدخل الإجمالي", "Gross income"), `${fmtJD(baseline.gross_income, lang)} JD`]);
          detail.push([L("الإعفاءات", "Exemptions"), `${fmtJD(baseline.total_exemptions, lang)} JD`]);
          detail.push([L("الدخل الخاضع", "Taxable income"), `${fmtJD(baseline.taxable_income, lang)} JD`]);
        }
        return { ...base, summary: L("تم تحليل الملف والدخل", "Profile & income parsed"), detail };
      }

      case "completeness": {
        const gaps = report.missing_fields ?? [];
        if (report.status === "incomplete") {
          const gapsText = gaps.map((f) => fieldLabel(f, lang)).join(listSep(lang));
          return {
            ...base,
            summary: L(`${gaps.length} نقص — بحاجة لإدخالك`, `${gaps.length} gap${gaps.length === 1 ? "" : "s"} — needs your input`),
            detail: [
              [L("تم الفحص", "Checked"), L("الملف، الدخل، الخصومات", "Profile, income, deductions")],
              [L("النواقص", "Gaps"), gaps.length ? gapsText : L("لا شيء", "none")],
              [L("المسار", "Route"), L("إيقاف → طلب إدخال", "Pause → request input")],
            ],
            branch: {
              title: L("بانتظار إدخالك", "Waiting on you"),
              line: gaps.length ? gapsText : L("أكمل ملفك الضريبي للمتابعة", "Complete your tax profile to continue"),
              cta: L("إضافة", "Add"),
            },
          };
        }
        return {
          ...base,
          summary: L("لا نواقص — كل السجلات موجودة", "No gaps — all records present"),
          detail: [
            [L("تم الفحص", "Checked"), L("الملف، الدخل، الخصومات", "Profile, income, deductions")],
            [L("الحالة", "Status"), L("مكتمل", "Complete")],
          ],
        };
      }

      case "deductions": {
        const allowed = baseline?.deductions_allowed ?? {};
        const entries = Object.entries(allowed).filter(([, v]) => v > 0);
        let detail: [string, string][];
        if (entries.length) {
          detail = entries.slice(0, 5).map(([c, v]) => [catLabel(c, lang), `${fmtJD(v, lang)} JD`]);
        } else {
          detail = (report.deduction_opportunities ?? [])
            .slice(0, 4)
            .map((o) => [
              catLabel(o.category, lang),
              o.estimated_savings != null ? `${fmtJD(o.estimated_savings, lang)} JD` : L("فرصة", "opportunity"),
            ]);
        }
        const total = baseline?.total_deductions ?? 0;
        return {
          ...base,
          summary: L(
            `${entries.length} فئات · ${fmtJD(total, lang)} دينار`,
            `${entries.length} categor${entries.length === 1 ? "y" : "ies"} · ${fmtJD(total, lang)} JD`,
          ),
          detail,
        };
      }

      case "scenarios": {
        const scenarios = report.scenarios ?? [];
        const bestTax = scenarios.length ? Math.min(...scenarios.map((s) => s.tax_liability)) : 0;
        const lanes: StepperLane[] = scenarios.map((s) => ({
          name: s.label,
          tax: fmtJD(s.tax_liability, lang),
          delta: s.delta_vs_baseline,
          best: s.tax_liability === bestTax,
        }));
        return {
          ...base,
          summary: L(`${lanes.length} استراتيجيات مقارنة`, `${lanes.length} strateg${lanes.length === 1 ? "y" : "ies"} compared`),
          lanes,
        };
      }

      case "risk": {
        const flags = report.risk_flags ?? [];
        const hasHigh = flags.some((f) => f.severity === "high");
        const top = flags.find((f) => f.severity === "high") ?? flags.find((f) => f.severity === "medium") ?? flags[0];
        const level = top ? pick(SEVERITY[top.severity], lang) : pick(SEVERITY.low, lang);
        const detail: [string, string][] = [[L("المستوى", "Level"), level]];
        flags.slice(0, 3).forEach((f) => detail.push([pick(SEVERITY[f.severity], lang), f.issue]));
        return {
          ...base,
          summary: L(`المخاطر: ${level}`, `Risk: ${level}`),
          detail,
          gatePass: !hasHigh,
          gateText: hasHigh
            ? L("تحذير — راجع البنود المرتفعة الخطورة", "Caution — review the high-severity items")
            : L("اجتاز البوابة — مخاطر تدقيق منخفضة", "Gate passed — low audit risk"),
        };
      }

      case "plan": {
        const steps = [...(report.action_plan ?? [])].sort((a, b) => a.priority - b.priority);
        const refund = baseline?.refund_due ?? 0;
        const net = baseline?.net_tax_due ?? 0;
        const detail: [string, string][] = [
          [L("الإجراءات", "Actions"), String(steps.length)],
        ];
        if (steps[0]) detail.push([L("أهم خطوة", "Top move"), steps[0].action]);
        detail.push([
          L("النتيجة", "Outcome"),
          refund > 0 ? `${L("استرداد", "Refund")} ${fmtJD(refund, lang)} JD` : `${L("مستحق", "Net due")} ${fmtJD(net, lang)} JD`,
        ]);
        return {
          ...base,
          summary: L(`${steps.length} إجراءات جاهزة`, `${steps.length} action${steps.length === 1 ? "" : "s"} ready`),
          detail,
        };
      }

      default:
        return base;
    }
  });
}

/* ============================================================
   useStepperRun — presentation clock.

   `active`  : index of running node; >= NODE_COUNT once done.
   `progress`: 0..1 within the active node (drives lane fills).
   `paused`  : true when an incomplete run settled at completeness.

   While `live` and the report has not yet arrived (`outcome === null`),
   the clock advances and HOLDS on the last node so the screen never
   claims "complete" before the data exists. When the report lands the
   clock settles to the real outcome.
   ============================================================ */
const prefersReduced = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export interface StepperRun {
  active: number;
  progress: number;
  paused: boolean;
}

export function useStepperRun(
  durations: number[],
  opts: {
    live: boolean;
    outcome: "complete" | "incomplete" | null;
    stopIndex: number; // node count completed when an incomplete run settles
    replayNonce: number;
  },
): StepperRun {
  const n = durations.length;
  const { live, outcome, stopIndex, replayNonce } = opts;
  const reduce = prefersReduced();

  const settledActive = outcome === "incomplete" ? stopIndex : n;
  const [active, setActive] = useState<number>(() => (live ? 0 : outcome ? settledActive : 0));
  const [progress, setProgress] = useState<number>(() => (live ? 0 : 1));
  const [paused, setPaused] = useState<boolean>(() => !live && outcome === "incomplete");

  const raf = useRef(0);
  const timer = useRef(0);
  const startAt = useRef(0);
  const outcomeRef = useRef(outcome);
  outcomeRef.current = outcome;
  const stopRef = useRef(stopIndex);
  stopRef.current = stopIndex;

  const clearTimers = useCallback(() => {
    cancelAnimationFrame(raf.current);
    clearTimeout(timer.current);
  }, []);

  const step = useCallback(
    (i: number) => {
      setPaused(false);
      setActive(i);
      if (i >= n) {
        setProgress(1);
        return;
      }
      startAt.current = performance.now();
      const dur = durations[i] || 1100;
      const loop = (now: number) => {
        const p = Math.min(1, (now - startAt.current) / dur);
        setProgress(p);
        if (p < 1) raf.current = requestAnimationFrame(loop);
      };
      raf.current = requestAnimationFrame(loop);
      timer.current = window.setTimeout(() => {
        const out = outcomeRef.current;
        const stop = stopRef.current;
        // incomplete: pause once the completeness node has run
        if (out === "incomplete" && i >= stop - 1) {
          clearTimers();
          setProgress(1);
          setActive(stop);
          setPaused(true);
          return;
        }
        if (i + 1 >= n) {
          if (out) {
            setProgress(1);
            setActive(n); // complete → done
          }
          // else: hold on the last node until the report arrives
          return;
        }
        step(i + 1);
      }, dur);
    },
    [durations, n, clearTimers],
  );

  const settleImmediate = useCallback(() => {
    clearTimers();
    setProgress(1);
    if (outcomeRef.current === "incomplete") {
      setActive(stopRef.current);
      setPaused(true);
    } else {
      setActive(n);
      setPaused(false);
    }
  }, [clearTimers, n]);

  // kickoff: a fresh run is in flight
  useEffect(() => {
    if (!live) return;
    if (reduce) {
      settleImmediate();
      return;
    }
    setPaused(false);
    step(0);
    return clearTimers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live]);

  // replay: report already present, re-watch the animation
  useEffect(() => {
    if (replayNonce === 0) return;
    if (reduce) {
      settleImmediate();
      return;
    }
    setPaused(false);
    step(0);
    return clearTimers;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replayNonce]);

  // settle when the report arrives (live run finishing) or when mounted with a cached report
  useEffect(() => {
    if (!outcome) return;
    if (live) return; // an in-flight run; the report has not landed yet
    settleImmediate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outcome, live]);

  useEffect(() => clearTimers, [clearTimers]);

  return { active, progress, paused };
}
