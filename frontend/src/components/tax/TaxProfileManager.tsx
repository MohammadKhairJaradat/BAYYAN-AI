import { Plus, RotateCw, Save, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useAuth } from "../../contexts/hooks";
import { useTaxProfile } from "../../contexts/hooks";
import type { TaxProfileSnapshot } from "../../contexts/TaxProfileContext";
import {
  createDeduction,
  createIncomeSource,
  deleteDeduction,
  deleteIncomeSource,
  getApiErrorMessage,
  getOrCreateCurrentTaxProfile,
  updateDeduction,
  updateIncomeSource,
  updateTaxProfile,
} from "../../services/api";
import type {
  AdvisorLang,
  BeneficiaryType,
  Deduction,
  DeductionCategory,
  FilingStatus,
  IncomeSource,
  IncomeType,
  MaritalStatus,
  ResidencyStatus,
  TaxProfile,
} from "../../types/api";
import { BENEFICIARY_CATEGORIES } from "../../types/api";

type ProfileForm = {
  marital_status: MaritalStatus;
  num_dependents: string;
  filing_status: FilingStatus;
  residency_status: ResidencyStatus;
  claims_dependents_exemption: boolean;
  claim_spouse_expense_exemption: boolean;
  disability_exemption_count: string;
};

type IncomeDraft = {
  type: IncomeType;
  amount: string;
  tax_withheld: string;
  employer_name: string;
  description: string;
};

type DeductionDraft = {
  category: DeductionCategory;
  amount: string;
  date: string;
  description: string;
  beneficiary: BeneficiaryType;
  beneficiary_name: string;
};

const beneficiaryTypes: BeneficiaryType[] = ["self", "spouse", "child"];

// Build the beneficiary fields for a create/update payload: only attach for
// medical/education, and only carry a name for spouse/child (display only — the
// tax engine ignores these).
function beneficiaryPayload(draft: { category: DeductionCategory; beneficiary: BeneficiaryType; beneficiary_name: string }) {
  if (!BENEFICIARY_CATEGORIES.includes(draft.category)) {
    return { beneficiary: null, beneficiary_name: null };
  }
  return {
    beneficiary: draft.beneficiary,
    beneficiary_name:
      draft.beneficiary === "self" ? null : draft.beneficiary_name.trim() || null,
  };
}

type Props = {
  compact?: boolean;
  lang?: AdvisorLang;
  onProfileChange?: (profile: TaxProfile | null) => void;
  onSaved?: (snapshot: TaxProfileSnapshot) => void | Promise<void>;
};

type IncomeLabels = Record<IncomeType, string>;
type DeductionLabels = Record<DeductionCategory, string>;
type ResidencyLabels = Record<ResidencyStatus, string>;
type BeneficiaryLabels = Record<BeneficiaryType, string> & {
  label: string;
  namePlaceholder: string;
  forPerson: string;
};

interface Strings {
  profileHeader: (year: number) => string;
  residency: string;
  maritalStatus: string;
  single: string;
  married: string;
  filingStatus: string;
  individual: string;
  joint: string;
  dependents: string;
  disabilityExemptions: string;
  claimFamilyExemption: string;
  claimSpouseExpense: string;
  createProfile: string;
  save: string;
  saveAndRerun: string;
  add: string;
  addAndRerun: string;
  delete: string;
  grossIncome: string;
  totalExemptions: string;
  taxWithheld: string;
  refundDue: string;
  netTaxDue: string;
  incomeSources: string;
  eligibleExpenses: string;
  amountPlaceholder: string;
  withheldPlaceholder: string;
  employerPlaceholder: string;
  descriptionPlaceholder: string;
  savedToast: string;
  savedRerunToast: string;
  errCreateProfile: string;
  errSaveProfile: string;
  errAddIncome: string;
  errSaveIncome: string;
  errDeleteIncome: string;
  errAddDeduction: string;
  errSaveDeduction: string;
  errDeleteDeduction: string;
  income: IncomeLabels;
  deduction: DeductionLabels;
  beneficiary: BeneficiaryLabels;
  residencyOptions: ResidencyLabels;
}

const T: Record<AdvisorLang, Strings> = {
  en: {
    profileHeader: (y) => `Tax profile ${y}`,
    residency: "Residency",
    maritalStatus: "Marital status",
    single: "Single",
    married: "Married",
    filingStatus: "Filing status",
    individual: "Individual",
    joint: "Joint",
    dependents: "Dependents",
    disabilityExemptions: "Disability exemptions",
    claimFamilyExemption: "Claim family exemption",
    claimSpouseExpense: "Claim spouse expense",
    createProfile: "Create profile",
    save: "Save",
    saveAndRerun: "Save & re-run",
    add: "Add",
    addAndRerun: "Add & re-run",
    delete: "Delete",
    grossIncome: "Gross income",
    totalExemptions: "Total exemptions",
    taxWithheld: "Tax withheld",
    refundDue: "Refund due",
    netTaxDue: "Net tax due",
    incomeSources: "Income sources",
    eligibleExpenses: "Eligible expenses and deductions",
    amountPlaceholder: "Amount",
    withheldPlaceholder: "Withheld",
    employerPlaceholder: "Employer",
    descriptionPlaceholder: "Description",
    savedToast: "Saved.",
    savedRerunToast: "Saved. Re-running advisor…",
    errCreateProfile: "Could not create tax profile.",
    errSaveProfile: "Could not save tax profile.",
    errAddIncome: "Could not add income.",
    errSaveIncome: "Could not save income.",
    errDeleteIncome: "Could not delete income.",
    errAddDeduction: "Could not add deduction.",
    errSaveDeduction: "Could not save deduction.",
    errDeleteDeduction: "Could not delete deduction.",
    income: {
      salary: "Salary",
      freelance: "Freelance",
      rental: "Rental",
      investment: "Investment",
    },
    deduction: {
      medical: "Medical",
      education: "Education",
      rent: "Rent",
      housing_interest: "Housing interest",
      housing_murabaha: "Housing murabaha",
      donations: "Approved donations",
      insurance: "Insurance",
      pension: "Pension",
    },
    beneficiary: {
      label: "For",
      self: "Self",
      spouse: "Spouse",
      child: "Child",
      namePlaceholder: "Name (optional)",
      forPerson: "For",
    },
    residencyOptions: {
      resident: "Resident",
      nonresident_jordanian: "Non-resident Jordanian",
      nonresident_other: "Other non-resident",
    },
  },
  ar: {
    profileHeader: (y) => `الملف الضريبي ${y}`,
    residency: "الإقامة",
    maritalStatus: "الحالة الاجتماعية",
    single: "أعزب/عزباء",
    married: "متزوج/ة",
    filingStatus: "نوع الإقرار",
    individual: "فردي",
    joint: "مشترك",
    dependents: "عدد المعالين",
    disabilityExemptions: "إعفاءات الإعاقة",
    claimFamilyExemption: "المطالبة بإعفاء عائلي",
    claimSpouseExpense: "المطالبة بنفقات الزوج/ة",
    createProfile: "إنشاء الملف",
    save: "حفظ",
    saveAndRerun: "حفظ وإعادة التشغيل",
    add: "إضافة",
    addAndRerun: "إضافة وإعادة التشغيل",
    delete: "حذف",
    grossIncome: "الدخل الإجمالي",
    totalExemptions: "إجمالي الإعفاءات",
    taxWithheld: "الضريبة المقتطعة",
    refundDue: "المبلغ المسترد",
    netTaxDue: "الصافي المستحق",
    incomeSources: "مصادر الدخل",
    eligibleExpenses: "المصاريف والخصومات المؤهلة",
    amountPlaceholder: "المبلغ",
    withheldPlaceholder: "المقتطع",
    employerPlaceholder: "جهة العمل",
    descriptionPlaceholder: "وصف",
    savedToast: "تم الحفظ.",
    savedRerunToast: "تم الحفظ. يجري إعادة تشغيل المستشار…",
    errCreateProfile: "تعذّر إنشاء الملف الضريبي.",
    errSaveProfile: "تعذّر حفظ الملف الضريبي.",
    errAddIncome: "تعذّر إضافة الدخل.",
    errSaveIncome: "تعذّر حفظ الدخل.",
    errDeleteIncome: "تعذّر حذف الدخل.",
    errAddDeduction: "تعذّر إضافة الخصم.",
    errSaveDeduction: "تعذّر حفظ الخصم.",
    errDeleteDeduction: "تعذّر حذف الخصم.",
    income: {
      salary: "راتب",
      freelance: "أعمال حرة",
      rental: "إيجار",
      investment: "استثمار",
    },
    deduction: {
      medical: "طبي",
      education: "تعليم",
      rent: "إيجار",
      housing_interest: "فوائد إسكان",
      housing_murabaha: "مرابحة إسكان",
      donations: "تبرعات معتمدة",
      insurance: "تأمين",
      pension: "تقاعد",
    },
    beneficiary: {
      label: "لِمَن",
      self: "المكلّف",
      spouse: "الزوج/ة",
      child: "الأبناء",
      namePlaceholder: "الاسم (اختياري)",
      forPerson: "لِـ",
    },
    residencyOptions: {
      resident: "مقيم",
      nonresident_jordanian: "أردني غير مقيم",
      nonresident_other: "غير مقيم آخر",
    },
  },
};

const incomeTypes: IncomeType[] = ["salary", "freelance", "rental", "investment"];
const deductionCategories: DeductionCategory[] = [
  "medical",
  "education",
  "rent",
  "housing_interest",
  "housing_murabaha",
  "donations",
  "insurance",
  "pension",
];
const residencyStatuses: ResidencyStatus[] = [
  "resident",
  "nonresident_jordanian",
  "nonresident_other",
];

function profileToForm(profile: TaxProfile | null): ProfileForm {
  return {
    marital_status: profile?.marital_status ?? "single",
    num_dependents: String(profile?.num_dependents ?? 0),
    filing_status: profile?.filing_status ?? "individual",
    residency_status: profile?.residency_status ?? "resident",
    claims_dependents_exemption: profile?.claims_dependents_exemption ?? false,
    claim_spouse_expense_exemption:
      profile?.claim_spouse_expense_exemption ?? false,
    disability_exemption_count: String(profile?.disability_exemption_count ?? 0),
  };
}

function fmtJD(n: number, lang: AdvisorLang): string {
  const locale = lang === "ar" ? "ar-JO" : "en-US";
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n);
}

function asText(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

function nonNegativeInt(value: string): number {
  const parsed = Number.parseInt(value || "0", 10);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function nonNegativeNumber(value: string): number {
  const parsed = Number.parseFloat(value || "0");
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

export function TaxProfileManager({
  compact = false,
  lang = "en",
  onProfileChange,
  onSaved,
}: Props) {
  const t = T[lang];
  const { user } = useAuth();
  const {
    currentYear,
    availableYears,
    selectYear,
    profile,
    incomeSources,
    deductions,
    calculation,
    loading,
    error: profileError,
    refreshTaxProfile,
  } = useTaxProfile();
  const [form, setForm] = useState<ProfileForm>(() => profileToForm(null));
  const [incomeRows, setIncomeRows] = useState<IncomeSource[]>([]);
  const [deductionRows, setDeductionRows] = useState<Deduction[]>([]);
  const [incomeDraft, setIncomeDraft] = useState<IncomeDraft>({
    type: "salary",
    amount: "",
    tax_withheld: "",
    employer_name: "",
    description: "",
  });
  const [deductionDraft, setDeductionDraft] = useState<DeductionDraft>({
    category: "medical",
    amount: "",
    date: "",
    description: "",
    beneficiary: "self",
    beneficiary_name: "",
  });
  const [busy, setBusy] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const saveLabel = onSaved ? t.saveAndRerun : t.save;
  const addLabel = onSaved ? t.addAndRerun : t.add;

  const publishProfileChange = useCallback(
    (snapshot: TaxProfileSnapshot) => {
      onProfileChange?.(snapshot.profile);
      return snapshot;
    },
    [onProfileChange],
  );

  const refreshAndPublish = useCallback(
    async () => publishProfileChange(await refreshTaxProfile()),
    [publishProfileChange, refreshTaxProfile],
  );

  const signalSaved = useCallback(async (snapshot: TaxProfileSnapshot) => {
    setToast(onSaved ? t.savedRerunToast : t.savedToast);
    setTimeout(() => setToast(null), 2500);
    await onSaved?.(snapshot);
  }, [onSaved, t.savedRerunToast, t.savedToast]);

  useEffect(() => {
    setForm(profileToForm(profile));
    onProfileChange?.(profile);
  }, [onProfileChange, profile]);

  useEffect(() => {
    setIncomeRows(incomeSources);
  }, [incomeSources]);

  useEffect(() => {
    setDeductionRows(deductions);
  }, [deductions]);

  async function handleCreateProfile() {
    if (!user) return;
    setBusy("profile");
    setErrorMsg(null);
    try {
      await getOrCreateCurrentTaxProfile(user.id, {
        marital_status: form.marital_status,
        num_dependents: nonNegativeInt(form.num_dependents),
        filing_status: form.filing_status,
        residency_status: form.residency_status,
        claims_dependents_exemption: form.claims_dependents_exemption,
        claim_spouse_expense_exemption: form.claim_spouse_expense_exemption,
        disability_exemption_count: nonNegativeInt(
          form.disability_exemption_count,
        ),
      }, currentYear);
      const snapshot = await refreshAndPublish();
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errCreateProfile));
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveProfile() {
    if (!profile) return;
    setBusy("profile");
    setErrorMsg(null);
    try {
      await updateTaxProfile(profile.id, {
        marital_status: form.marital_status,
        num_dependents: nonNegativeInt(form.num_dependents),
        filing_status: form.filing_status,
        residency_status: form.residency_status,
        claims_dependents_exemption: form.claims_dependents_exemption,
        claim_spouse_expense_exemption: form.claim_spouse_expense_exemption,
        disability_exemption_count: nonNegativeInt(
          form.disability_exemption_count,
        ),
      }, profile.version);
      const snapshot = await refreshAndPublish();
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errSaveProfile));
    } finally {
      setBusy(null);
    }
  }

  async function handleAddIncome() {
    if (!profile) return;
    const amount = nonNegativeNumber(incomeDraft.amount);
    if (amount <= 0) return;
    setBusy("add-income");
    setErrorMsg(null);
    try {
      await createIncomeSource({
        tax_profile_id: profile.id,
        type: incomeDraft.type,
        amount,
        tax_withheld: nonNegativeNumber(incomeDraft.tax_withheld),
        employer_name: incomeDraft.employer_name.trim() || null,
        description: incomeDraft.description.trim() || null,
      }, profile.version);
      const snapshot = await refreshAndPublish();
      setIncomeDraft({
        type: "salary",
        amount: "",
        tax_withheld: "",
        employer_name: "",
        description: "",
      });
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errAddIncome));
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveIncome(row: IncomeSource) {
    setBusy(`income-${row.id}`);
    setErrorMsg(null);
    try {
      await updateIncomeSource(row.id, {
        type: row.type,
        amount: nonNegativeNumber(asText(row.amount)),
        tax_withheld: nonNegativeNumber(asText(row.tax_withheld)),
        employer_name: row.employer_name?.trim() || null,
        description: row.description?.trim() || null,
      }, profile?.version);
      const snapshot = await refreshAndPublish();
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errSaveIncome));
    } finally {
      setBusy(null);
    }
  }

  async function handleDeleteIncome(id: string) {
    setBusy(`income-${id}`);
    setErrorMsg(null);
    try {
      await deleteIncomeSource(id, profile?.version);
      const snapshot = await refreshAndPublish();
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errDeleteIncome));
    } finally {
      setBusy(null);
    }
  }

  async function handleAddDeduction() {
    if (!profile) return;
    const amount = nonNegativeNumber(deductionDraft.amount);
    if (amount <= 0) return;
    setBusy("add-deduction");
    setErrorMsg(null);
    try {
      await createDeduction({
        tax_profile_id: profile.id,
        category: deductionDraft.category,
        amount,
        date: deductionDraft.date || null,
        description: deductionDraft.description.trim() || null,
        ...beneficiaryPayload(deductionDraft),
      }, profile.version);
      const snapshot = await refreshAndPublish();
      setDeductionDraft({
        category: "medical",
        amount: "",
        date: "",
        description: "",
        beneficiary: "self",
        beneficiary_name: "",
      });
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errAddDeduction));
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveDeduction(row: Deduction) {
    setBusy(`deduction-${row.id}`);
    setErrorMsg(null);
    try {
      await updateDeduction(row.id, {
        category: row.category,
        amount: nonNegativeNumber(asText(row.amount)),
        date: row.date || null,
        description: row.description?.trim() || null,
        ...beneficiaryPayload({
          category: row.category,
          beneficiary: (row.beneficiary as BeneficiaryType | null) ?? "self",
          beneficiary_name: row.beneficiary_name ?? "",
        }),
        document_id: row.document_id ?? null,
      }, profile?.version);
      const snapshot = await refreshAndPublish();
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errSaveDeduction));
    } finally {
      setBusy(null);
    }
  }

  async function handleDeleteDeduction(id: string) {
    setBusy(`deduction-${id}`);
    setErrorMsg(null);
    try {
      await deleteDeduction(id, profile?.version);
      const snapshot = await refreshAndPublish();
      await signalSaved(snapshot);
    } catch (error) {
      setErrorMsg(getApiErrorMessage(error, t.errDeleteDeduction));
    } finally {
      setBusy(null);
    }
  }

  const visibleError = errorMsg ?? profileError;

  if (loading && !profile) {
    return (
      <div style={{ display: "grid", placeItems: "center", padding: "40px 0" }}>
        <div style={{ width: 30, height: 30, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)", animation: "spin 1s linear infinite" }} />
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  return (
    <div className={compact ? "space-y-5" : "space-y-7"}>
      {visibleError && (
        <div className="t-small" style={{ color: "var(--danger)", background: "var(--clay-tint)", borderRadius: 10, padding: "10px 14px" }}>
          {visibleError}
        </div>
      )}
      {toast && (
        <div className="t-small" style={{ color: "var(--positive)", background: "var(--green-tint)", borderRadius: 10, padding: "10px 14px" }}>
          {toast}
        </div>
      )}

      <section className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <SectionHeader title={t.profileHeader(currentYear)} />
          <select
            aria-label={lang === "ar" ? "السنة الضريبية" : "Tax year"}
            value={currentYear}
            onChange={(event) => { setErrorMsg(null); selectYear(Number(event.target.value)); }}
            className={inputClass}
            style={{ maxWidth: 140 }}
          >
            {availableYears.map((year) => <option key={year} value={year}>{year}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label={t.residency}>
            <select
              value={form.residency_status}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  residency_status: e.target.value as ResidencyStatus,
                }))
              }
              className={inputClass}
            >
              {residencyStatuses.map((status) => (
                <option key={status} value={status}>
                  {t.residencyOptions[status]}
                </option>
              ))}
            </select>
          </Field>
          <Field label={t.maritalStatus}>
            <select
              value={form.marital_status}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  marital_status: e.target.value as MaritalStatus,
                }))
              }
              className={inputClass}
            >
              <option value="single">{t.single}</option>
              <option value="married">{t.married}</option>
            </select>
          </Field>
          <Field label={t.filingStatus}>
            <select
              value={form.filing_status}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  filing_status: e.target.value as FilingStatus,
                }))
              }
              className={inputClass}
            >
              <option value="individual">{t.individual}</option>
              <option value="joint">{t.joint}</option>
            </select>
          </Field>
          <Field label={t.dependents}>
            <input
              type="number"
              min={0}
              max={20}
              value={form.num_dependents}
              onChange={(e) =>
                setForm((p) => ({ ...p, num_dependents: e.target.value }))
              }
              className={inputClass}
            />
          </Field>
          <Field label={t.disabilityExemptions}>
            <input
              type="number"
              min={0}
              max={20}
              value={form.disability_exemption_count}
              onChange={(e) =>
                setForm((p) => ({
                  ...p,
                  disability_exemption_count: e.target.value,
                }))
              }
              className={inputClass}
            />
          </Field>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ToggleRow
              label={t.claimFamilyExemption}
              checked={form.claims_dependents_exemption}
              onChange={(checked) =>
                setForm((p) => ({
                  ...p,
                  claims_dependents_exemption: checked,
                }))
              }
            />
            <ToggleRow
              label={t.claimSpouseExpense}
              checked={form.claim_spouse_expense_exemption}
              onChange={(checked) =>
                setForm((p) => ({
                  ...p,
                  claim_spouse_expense_exemption: checked,
                }))
              }
            />
          </div>
        </div>
        <div className="flex justify-end">
          <ActionButton
            busy={busy === "profile"}
            disabled={busy !== null || loading}
            onClick={profile ? handleSaveProfile : handleCreateProfile}
            icon={<Save className="w-4 h-4" />}
          >
            {profile ? saveLabel : t.createProfile}
          </ActionButton>
        </div>
      </section>

      {calculation && (
        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Metric label={t.grossIncome} value={`${fmtJD(calculation.gross_income, lang)} JD`} />
          <Metric
            label={t.totalExemptions}
            value={`${fmtJD(calculation.total_exemptions, lang)} JD`}
          />
          <Metric
            label={t.taxWithheld}
            value={`${fmtJD(calculation.total_tax_withheld, lang)} JD`}
          />
          <Metric
            label={calculation.refund_due > 0 ? t.refundDue : t.netTaxDue}
            value={`${fmtJD(
              calculation.refund_due > 0
                ? calculation.refund_due
                : calculation.net_tax_due,
              lang,
            )} JD`}
          />
        </section>
      )}

      {profile && (
        <>
          <section className="space-y-4">
            <SectionHeader title={t.incomeSources} />
            <div className="space-y-3">
              {incomeRows.map((row) => (
                <IncomeRow
                  key={row.id}
                  row={row}
                  busy={busy === `income-${row.id}`}
                  disabled={busy !== null}
                  onChange={(next) =>
                    setIncomeRows((rows) =>
                      rows.map((item) => (item.id === row.id ? next : item)),
                    )
                  }
                  onSave={() => handleSaveIncome(row)}
                  onDelete={() => handleDeleteIncome(row.id)}
                  saveLabel={saveLabel}
                  deleteLabel={t.delete}
                  incomeLabels={t.income}
                />
              ))}
              <div style={rowCard} className="grid grid-cols-1 md:grid-cols-5 gap-3">
                <select
                  value={incomeDraft.type}
                  onChange={(e) =>
                    setIncomeDraft((p) => ({
                      ...p,
                      type: e.target.value as IncomeType,
                    }))
                  }
                  className={inputClass}
                >
                  {incomeTypes.map((type) => (
                    <option key={type} value={type}>
                      {t.income[type]}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={0}
                  step={100}
                  placeholder={t.amountPlaceholder}
                  value={incomeDraft.amount}
                  onChange={(e) =>
                    setIncomeDraft((p) => ({ ...p, amount: e.target.value }))
                  }
                  className={inputClass}
                />
                <input
                  type="number"
                  min={0}
                  step={10}
                  placeholder={t.withheldPlaceholder}
                  value={incomeDraft.tax_withheld}
                  onChange={(e) =>
                    setIncomeDraft((p) => ({
                      ...p,
                      tax_withheld: e.target.value,
                    }))
                  }
                  className={inputClass}
                />
                <input
                  type="text"
                  placeholder={t.employerPlaceholder}
                  value={incomeDraft.employer_name}
                  onChange={(e) =>
                    setIncomeDraft((p) => ({
                      ...p,
                      employer_name: e.target.value,
                    }))
                  }
                  className={inputClass}
                />
                <ActionButton
                  busy={busy === "add-income"}
                  disabled={busy !== null || !incomeDraft.amount}
                  onClick={handleAddIncome}
                  icon={<Plus className="w-4 h-4" />}
                >
                  {addLabel}
                </ActionButton>
              </div>
            </div>
          </section>

          <section className="space-y-4">
            <SectionHeader title={t.eligibleExpenses} />
            {(() => {
              // Per-person view of medical/education spend (display only — the
              // engine pools by category and ignores the beneficiary).
              const groups = new Map<string, number>();
              for (const r of deductionRows) {
                if (!BENEFICIARY_CATEGORIES.includes(r.category) || !r.beneficiary)
                  continue;
                const who =
                  r.beneficiary === "self"
                    ? t.beneficiary.self
                    : `${t.beneficiary[r.beneficiary as BeneficiaryType]}${
                        r.beneficiary_name ? ` · ${r.beneficiary_name}` : ""
                      }`;
                groups.set(
                  who,
                  (groups.get(who) ?? 0) + nonNegativeNumber(asText(r.amount)),
                );
              }
              if (groups.size === 0) return null;
              return (
                <p className="text-xs" style={{ opacity: 0.7 }}>
                  {[...groups.entries()]
                    .map(([who, sum]) => `${who}: ${fmtJD(sum, lang)} JD`)
                    .join("   ·   ")}
                </p>
              );
            })()}
            <div className="space-y-3">
              {deductionRows.map((row) => (
                <DeductionRow
                  key={row.id}
                  row={row}
                  busy={busy === `deduction-${row.id}`}
                  disabled={busy !== null}
                  onChange={(next) =>
                    setDeductionRows((rows) =>
                      rows.map((item) => (item.id === row.id ? next : item)),
                    )
                  }
                  onSave={() => handleSaveDeduction(row)}
                  onDelete={() => handleDeleteDeduction(row.id)}
                  saveLabel={saveLabel}
                  deleteLabel={t.delete}
                  deductionLabels={t.deduction}
                  beneficiaryLabels={t.beneficiary}
                />
              ))}
              <div style={rowCard} className="flex flex-col gap-3">
                <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                  <select
                    value={deductionDraft.category}
                    onChange={(e) =>
                      setDeductionDraft((p) => ({
                        ...p,
                        category: e.target.value as DeductionCategory,
                      }))
                    }
                    className={inputClass}
                  >
                    {deductionCategories.map((category) => (
                      <option key={category} value={category}>
                        {t.deduction[category]}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    min={0}
                    step={10}
                    placeholder={t.amountPlaceholder}
                    value={deductionDraft.amount}
                    onChange={(e) =>
                      setDeductionDraft((p) => ({
                        ...p,
                        amount: e.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                  <input
                    type="date"
                    value={deductionDraft.date}
                    onChange={(e) =>
                      setDeductionDraft((p) => ({ ...p, date: e.target.value }))
                    }
                    className={inputClass}
                  />
                  <input
                    type="text"
                    placeholder={t.descriptionPlaceholder}
                    value={deductionDraft.description}
                    onChange={(e) =>
                      setDeductionDraft((p) => ({
                        ...p,
                        description: e.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                  <ActionButton
                    busy={busy === "add-deduction"}
                    disabled={busy !== null || !deductionDraft.amount}
                    onClick={handleAddDeduction}
                    icon={<Plus className="w-4 h-4" />}
                  >
                    {addLabel}
                  </ActionButton>
                </div>
                {BENEFICIARY_CATEGORIES.includes(deductionDraft.category) && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <select
                      value={deductionDraft.beneficiary}
                      onChange={(e) =>
                        setDeductionDraft((p) => ({
                          ...p,
                          beneficiary: e.target.value as BeneficiaryType,
                        }))
                      }
                      className={inputClass}
                      aria-label={t.beneficiary.label}
                    >
                      {beneficiaryTypes.map((b) => (
                        <option key={b} value={b}>
                          {t.beneficiary.label}: {t.beneficiary[b]}
                        </option>
                      ))}
                    </select>
                    {deductionDraft.beneficiary !== "self" && (
                      <input
                        type="text"
                        placeholder={t.beneficiary.namePlaceholder}
                        value={deductionDraft.beneficiary_name}
                        onChange={(e) =>
                          setDeductionDraft((p) => ({
                            ...p,
                            beneficiary_name: e.target.value,
                          }))
                        }
                        className={inputClass}
                      />
                    )}
                  </div>
                )}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

const inputClass = "input";
const rowCard: React.CSSProperties = {
  borderRadius: 12,
  border: "1px solid var(--line)",
  background: "var(--paper-2)",
  padding: 16,
};

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="row-between" style={{ gap: 12 }}>
      <h2 className="t-eyebrow">{title}</h2>
    </div>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label
      className="row-between"
      style={{ gap: 12, borderRadius: 10, border: "1px solid var(--line)", background: "var(--paper-2)", padding: "10px 13px" }}
    >
      <span className="t-small" style={{ color: "var(--ink)" }}>
        {label}
      </span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 16, height: 16, accentColor: "var(--green)" }}
      />
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ borderRadius: 12, border: "1px solid var(--line)", background: "var(--paper-2)", padding: 16 }}>
      <div className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10, marginBottom: 4 }}>
        {label}
      </div>
      <div className="num" style={{ fontSize: 18, fontWeight: 600 }}>
        {value}
      </div>
    </div>
  );
}

function ActionButton({
  children,
  busy,
  disabled,
  icon,
  onClick,
  tone = "primary",
}: {
  children: ReactNode;
  busy: boolean;
  disabled: boolean;
  icon: ReactNode;
  onClick: () => void;
  tone?: "primary" | "danger";
}) {
  return (
    <button
      type="button"
      disabled={busy || disabled}
      onClick={onClick}
      className={`btn btn-sm ${tone === "danger" ? "btn-ghost" : "btn-primary"}`}
      style={tone === "danger" ? { color: "var(--danger)", borderColor: "var(--danger)" } : undefined}
    >
      {busy ? <RotateCw className="w-4 h-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

function IncomeRow({
  row,
  busy,
  disabled,
  onChange,
  onSave,
  onDelete,
  saveLabel,
  deleteLabel,
  incomeLabels,
}: {
  row: IncomeSource;
  busy: boolean;
  disabled: boolean;
  onChange: (row: IncomeSource) => void;
  onSave: () => void;
  onDelete: () => void;
  saveLabel: string;
  deleteLabel: string;
  incomeLabels: IncomeLabels;
}) {
  return (
    <div style={rowCard} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_1fr_auto_auto] gap-3">
      <select
        value={row.type}
        onChange={(e) => onChange({ ...row, type: e.target.value as IncomeType })}
        className={inputClass}
      >
        {incomeTypes.map((type) => (
          <option key={type} value={type}>
            {incomeLabels[type]}
          </option>
        ))}
      </select>
      <input
        type="number"
        min={0}
        step={100}
        value={asText(row.amount)}
        onChange={(e) => onChange({ ...row, amount: e.target.value })}
        className={inputClass}
      />
      <input
        type="number"
        min={0}
        step={10}
        value={asText(row.tax_withheld)}
        onChange={(e) => onChange({ ...row, tax_withheld: e.target.value })}
        className={inputClass}
      />
      <input
        type="text"
        value={row.employer_name ?? ""}
        onChange={(e) => onChange({ ...row, employer_name: e.target.value })}
        className={inputClass}
      />
      <ActionButton
        busy={busy}
        disabled={disabled}
        onClick={onSave}
        icon={<Save className="w-4 h-4" />}
      >
        {saveLabel}
      </ActionButton>
      <ActionButton
        busy={busy}
        disabled={disabled}
        onClick={onDelete}
        icon={<Trash2 className="w-4 h-4" />}
        tone="danger"
      >
        {deleteLabel}
      </ActionButton>
    </div>
  );
}

function DeductionRow({
  row,
  busy,
  disabled,
  onChange,
  onSave,
  onDelete,
  saveLabel,
  deleteLabel,
  deductionLabels,
  beneficiaryLabels,
}: {
  row: Deduction;
  busy: boolean;
  disabled: boolean;
  onChange: (row: Deduction) => void;
  onSave: () => void;
  onDelete: () => void;
  saveLabel: string;
  deleteLabel: string;
  deductionLabels: DeductionLabels;
  beneficiaryLabels: BeneficiaryLabels;
}) {
  const showBeneficiary = BENEFICIARY_CATEGORIES.includes(row.category);
  const beneficiary = (row.beneficiary as BeneficiaryType | null) ?? "self";
  return (
    <div style={rowCard} className="flex flex-col gap-3">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_1fr_auto_auto] gap-3">
        <select
          value={row.category}
          onChange={(e) =>
            onChange({ ...row, category: e.target.value as DeductionCategory })
          }
          className={inputClass}
        >
          {deductionCategories.map((category) => (
            <option key={category} value={category}>
              {deductionLabels[category]}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={0}
          step={10}
          value={asText(row.amount)}
          onChange={(e) => onChange({ ...row, amount: e.target.value })}
          className={inputClass}
        />
        <input
          type="date"
          value={row.date ?? ""}
          onChange={(e) => onChange({ ...row, date: e.target.value || null })}
          className={inputClass}
        />
        <input
          type="text"
          value={row.description ?? ""}
          onChange={(e) => onChange({ ...row, description: e.target.value })}
          className={inputClass}
        />
        <ActionButton
          busy={busy}
          disabled={disabled}
          onClick={onSave}
          icon={<Save className="w-4 h-4" />}
        >
          {saveLabel}
        </ActionButton>
        <ActionButton
          busy={busy}
          disabled={disabled}
          onClick={onDelete}
          icon={<Trash2 className="w-4 h-4" />}
          tone="danger"
        >
          {deleteLabel}
        </ActionButton>
      </div>
      {showBeneficiary && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <select
            value={beneficiary}
            onChange={(e) =>
              onChange({ ...row, beneficiary: e.target.value as BeneficiaryType })
            }
            className={inputClass}
            aria-label={beneficiaryLabels.label}
          >
            {beneficiaryTypes.map((b) => (
              <option key={b} value={b}>
                {beneficiaryLabels.label}: {beneficiaryLabels[b]}
              </option>
            ))}
          </select>
          {beneficiary !== "self" && (
            <input
              type="text"
              placeholder={beneficiaryLabels.namePlaceholder}
              value={row.beneficiary_name ?? ""}
              onChange={(e) =>
                onChange({ ...row, beneficiary_name: e.target.value })
              }
              className={inputClass}
            />
          )}
        </div>
      )}
    </div>
  );
}
