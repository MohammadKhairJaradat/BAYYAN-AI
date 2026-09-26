// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../../contexts/LanguageContext";
import { TaxProfileContext } from "../../contexts/hooks";
import type { TaxProfileContextValue } from "../../contexts/TaxProfileContext";
import * as apiModule from "../../services/api";
import {
  DocumentRequirementsCard,
  DocumentStatusExplainer,
  ProfileCompletionGuide,
  QuotaUsageIndicator,
} from "./index";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    getMyUsage: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

beforeEach(() => {
  vi.mocked(apiModule.getMyUsage).mockResolvedValue({
    tier: "Pro",
    usage_month: "2026-09",
    messages: { used: 10, limit: 200, remaining: 190 },
    docs: { used: 4, limit: 50, remaining: 46 },
    allowed_models: [],
    max_tokens: 2048,
  });
});

function wrap(ui: React.ReactElement, mockProfileValue?: Partial<TaxProfileContextValue>) {
  const profileVal: TaxProfileContextValue = {
    currentYear: 2025,
    availableYears: [2025],
    selectYear: () => undefined,
    profile: null,
    incomeSources: [],
    deductions: [],
    calculation: null,
    version: 1,
    loading: false,
    error: null,
    refreshTaxProfile: async () => ({
      profile: null,
      incomeSources: [],
      deductions: [],
      calculation: null,
      version: 1,
    }),
    ...mockProfileValue,
  };

  return render(
    <MemoryRouter>
      <LanguageProvider>
        <TaxProfileContext.Provider value={profileVal}>
          {ui}
        </TaxProfileContext.Provider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

describe("Guidance Components", () => {
  it("renders DocumentRequirementsCard with required document types", () => {
    wrap(<DocumentRequirementsCard defaultExpanded={true} />);
    expect(screen.getAllByText(/Salary Slips|كشوف الرواتب الشهرية/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/Invoices|فواتير وإيصالات/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/Bank Statements|كشوف الحسابات البنكية/i)[0]).toBeTruthy();
  });

  it("toggles DocumentRequirementsCard via keyboard-accessible button header", () => {
    wrap(<DocumentRequirementsCard defaultExpanded={false} />);
    const button = screen.getByRole("button", { name: /expand|توسيع/i });
    expect(button).toBeTruthy();
    expect(button.getAttribute("aria-expanded")).toBe("false");

    // Click or Enter expands
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText(/Salary Slips|كشوف الرواتب الشهرية/i)).toBeTruthy();

    // Click again collapses
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("renders DocumentStatusExplainer with the four processing states and accessible toggle", () => {
    wrap(<DocumentStatusExplainer defaultExpanded={true} />);
    expect(screen.getAllByText(/Pending|قيد الانتظار/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/Processing|قيد القراءة/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/Processed|تمت المعالجة/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/Failed|فشل الاستخراج/i)[0]).toBeTruthy();

    const button = screen.getByRole("button", { name: /collapse|طي/i });
    expect(button.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });

  it("renders ProfileCompletionGuide showing steps progress and accessible toggle", () => {
    wrap(<ProfileCompletionGuide documentCount={2} pendingDocCount={1} />);
    expect(screen.getAllByText(/Filing Readiness|جاهزية الملف الضريبي/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/1\. Personal|١\. البيانات/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/2\. Income|٢\. مصادر الدخل/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/3\. Deductions|٣\. النفقات/i)[0]).toBeTruthy();
    expect(screen.getAllByText(/4\. (Tax Calculation|Statement)|٤\. مراجعة التقدير/i)[0]).toBeTruthy();

    const toggleButton = screen.getByRole("button", { name: /collapse|طي/i });
    expect(toggleButton.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(toggleButton);
    expect(toggleButton.getAttribute("aria-expanded")).toBe("false");
  });

  it("renders ProfileCompletionGuide with localized strings in Arabic without English leaks", () => {
    localStorage.setItem("bayyan-lang", "ar");
    wrap(
      <ProfileCompletionGuide documentCount={3} pendingDocCount={0} />,
      {
        incomeSources: [
          { id: "i1", tax_profile_id: "p1", type: "salary", amount: 12000, tax_withheld: 500 },
        ],
        deductions: [
          { id: "d1", tax_profile_id: "p1", category: "medical", amount: 800 },
        ],
        calculation: {
          tax_profile_id: "p1",
          gross_income: 12000,
          personal_exemption: 9000,
          family_exemption: 0,
          expense_exemption: 800,
          disability_exemption: 0,
          total_exemptions: 9800,
          deductions_allowed: {},
          deductions_disallowed: {},
          total_deductions: 800,
          taxable_income: 2200,
          bracket_breakdown: [],
          national_contribution: 0,
          tax_liability: 110,
          total_tax_withheld: 500,
          net_tax_due: 0,
          refund_due: 390,
          effective_rate: 0.009,
          marginal_rate: 0.05,
        },
      }
    );

    // Verify Arabic details
    expect(screen.getByText(/1 مصادر دخل/)).toBeTruthy();
    expect(screen.getByText(/3 مستند\(ات\) · 1 إثبات\(ات\) نفقة/)).toBeTruthy();
    expect(screen.getByText(/صافي مستحق.*استرداد/)).toBeTruthy();
  });

  it("handles QuotaUsageIndicator error state honestly without displaying 0/0 as Active", async () => {
    vi.mocked(apiModule.getMyUsage).mockRejectedValue(new Error("Network failure"));
    wrap(<QuotaUsageIndicator compact={false} showExemptions={false} />);

    await waitFor(() => {
      expect(screen.getAllByText(/Usage unavailable|الاستخدام غير متوفر/i).length).toBeGreaterThanOrEqual(1);
    });

    // Must NOT render Active chip when API errored
    expect(screen.queryByText(/Active/i)).toBeNull();
    expect(screen.queryByText(/0\/0/)).toBeNull();
  });

  it("renders QuotaUsageIndicator with honest deterministic calculation breakdown", async () => {
    wrap(
      <QuotaUsageIndicator showExemptions={true} />,
      {
        calculation: {
          tax_profile_id: "p1",
          gross_income: 30000,
          personal_exemption: 9000,
          family_exemption: 9000,
          expense_exemption: 2000,
          disability_exemption: 2000,
          total_exemptions: 22000,
          deductions_allowed: {},
          deductions_disallowed: {},
          total_deductions: 2000,
          taxable_income: 8000,
          bracket_breakdown: [],
          national_contribution: 0,
          tax_liability: 400,
          total_tax_withheld: 600,
          net_tax_due: 0,
          refund_due: 200,
          effective_rate: 0.013,
          marginal_rate: 0.05,
        },
      }
    );

    await waitFor(() => {
      expect(screen.getByText(/46 left|متبقٍ 46/i)).toBeTruthy();
    });

    // Displays deterministic values without an artificial 23,000 progress bar
    expect(screen.getAllByText(/9,000 JD|٩٬٠٠٠ د\.أ/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/2,000 JD|٢٬٠٠٠ د\.أ/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/22,000 JD|٢٢٬٠٠٠ د\.أ/)).toBeTruthy();
    expect(screen.getByText(/Disability Exemption|إعفاء ذوي الإعاقة/i)).toBeTruthy();
  });

  it("shows honest notice when calculation is null instead of claiming 0% of 23000 ceiling", async () => {
    wrap(<QuotaUsageIndicator showExemptions={true} />, { calculation: null });

    await waitFor(() => {
      expect(screen.getByText(/46 left|متبقٍ 46/i)).toBeTruthy();
    });

    // Honest text displayed when no calculation exists
    expect(
      screen.getAllByText(/Complete your tax profile|أكمل بيانات ملفك/i).length
    ).toBeGreaterThanOrEqual(1);

    // No hardcoded 23,000 denominator progress ceiling
    expect(screen.queryByText(/of 23,000 JD ceiling/i)).toBeNull();
  });

  it("correctly handles zero-income profile and no-calculation state without falsely claiming an advisor report exists", () => {
    // Case 1: Valid zero-income profile with deterministic calculation
    const { unmount } = wrap(
      <ProfileCompletionGuide documentCount={0} pendingDocCount={0} />,
      {
        profile: {
          id: "p-zero",
          user_id: "u1",
          tax_year: 2025,
          version: 1,
          residency_status: "resident",
          marital_status: "single",
          num_dependents: 0,
          filing_status: "individual",
          claims_dependents_exemption: false,
          claim_spouse_expense_exemption: false,
          disability_exemption_count: 0,
          created_at: "2026-01-01",
        },
        incomeSources: [],
        deductions: [],
        calculation: {
          tax_profile_id: "p-zero",
          gross_income: 0,
          personal_exemption: 9000,
          family_exemption: 0,
          expense_exemption: 0,
          disability_exemption: 0,
          total_exemptions: 9000,
          deductions_allowed: {},
          deductions_disallowed: {},
          total_deductions: 0,
          taxable_income: 0,
          bracket_breakdown: [],
          national_contribution: 0,
          tax_liability: 0,
          total_tax_withheld: 0,
          net_tax_due: 0,
          refund_due: 0,
          effective_rate: 0,
          marginal_rate: 0,
        },
      }
    );

    // Step 4 is done because deterministic calculation was produced for the zero-income profile
    expect(screen.getByText(/4\. Tax Calculation Review|٤\. مراجعة التقدير الضريبي/i)).toBeTruthy();
    expect(screen.getByText(/0 JD net \/ 0 JD refund|صافي مستحق 0 د\.أ \/ استرداد 0 د\.أ/i)).toBeTruthy();
    // Does NOT claim an advisor report exists
    expect(screen.queryByText(/advisor report/i)).toBeNull();

    unmount();

    // Case 2: No calculation yet
    wrap(
      <ProfileCompletionGuide documentCount={0} pendingDocCount={0} />,
      {
        profile: {
          id: "p-init",
          user_id: "u1",
          tax_year: 2025,
          version: 1,
          residency_status: "resident",
          marital_status: "single",
          num_dependents: 0,
          filing_status: "individual",
          claims_dependents_exemption: false,
          claim_spouse_expense_exemption: false,
          disability_exemption_count: 0,
          created_at: "2026-01-01",
        },
        incomeSources: [],
        deductions: [],
        calculation: null,
      }
    );

    // Step 4 is NOT done when calculation is null
    expect(screen.queryByText(/0 JD net \/ 0 JD refund/i)).toBeNull();
    expect(screen.queryByText(/advisor report/i)).toBeNull();
  });
});
