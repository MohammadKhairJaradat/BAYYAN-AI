// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../../contexts/LanguageContext";
import { TaxProfileContext } from "../../contexts/hooks";
import type { TaxProfileContextValue } from "../../contexts/TaxProfileContext";
import * as apiModule from "../../services/api";
import TaxYearSummary from "./TaxYearSummary";
import type { TaxProfile, TaxWorkspacePreview } from "../../types/api";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    previewTaxWorkspace: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

function wrap(ui: React.ReactElement, mockProfileValue?: Partial<TaxProfileContextValue>) {
  const defaultProfile: TaxProfile = {
    id: "profile-1",
    user_id: "user-1",
    tax_year: 2026,
    residency_status: "resident",
    marital_status: "married",
    num_dependents: 2,
    filing_status: "individual",
    claims_dependents_exemption: true,
    claim_spouse_expense_exemption: false,
    disability_exemption_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    version: 2,
  };

  const profileVal: TaxProfileContextValue = {
    currentYear: 2026,
    availableYears: [2026, 2025],
    selectYear: vi.fn(),
    profile: defaultProfile,
    incomeSources: [],
    deductions: [],
    calculation: null,
    version: 2,
    loading: false,
    error: null,
    refreshTaxProfile: async () => ({
      profile: defaultProfile,
      incomeSources: [],
      deductions: [],
      calculation: null,
      version: 2,
    }),
    ...mockProfileValue,
  };

  return {
    ...render(
      <MemoryRouter>
        <LanguageProvider>
          <TaxProfileContext.Provider value={profileVal}>
            {ui}
          </TaxProfileContext.Provider>
        </LanguageProvider>
      </MemoryRouter>
    ),
    selectYearMock: profileVal.selectYear,
  };
}

describe("TaxYearSummary Component (Card G-WORKSPACE01)", () => {
  beforeEach(() => {
    vi.mocked(apiModule.previewTaxWorkspace).mockResolvedValue({
      tax_year: 2026,
      profile_id: "profile-1",
      profile_version: 2,
      input_snapshot: {},
      preview: {
        gross_income: "12000.000",
        total_exemptions: "9000.000",
        taxable_income: "3000.000",
        tax_liability: "150.000",
        total_tax_withheld: "0.000",
        net_tax_due: "150.000",
        refund_due: "0.000",
        ruleset_id: "bayyan-demo-legacy-v1",
        official_filing: false,
      },
      latest_run: null,
    });
  });

  it("renders server-backed facts and handles no-run state (latest_run === null)", async () => {
    wrap(<TaxYearSummary />);

    await waitFor(() => {
      expect(screen.getByTestId("tax-year-summary-card")).toBeTruthy();
    });

    // Verify ruleset badge and profile version
    expect(screen.getByText(/bayyan-demo-legacy-v1/)).toBeTruthy();
    expect(screen.getByText(/v2/)).toBeTruthy();
    expect(screen.getByText(/ليس إقراراً رسمياً|Not an official filing/i)).toBeTruthy();

    // Verify no-run status
    expect(screen.getByText(/لم يُحفظ بعد|Not calculated \/ saved/i)).toBeTruthy();
    expect(screen.getByText(/لا توجد لقطة احتساب محفوظة|No saved calculation snapshot exists/i)).toBeTruthy();

    // Verify preview numbers
    expect(screen.getByText(/12,000/)).toBeTruthy();
    expect(screen.getByText(/9,000/)).toBeTruthy();
    expect(screen.getByText(/3,000/)).toBeTruthy();
  });

  it("handles zero-income state with statutory allowance notice", async () => {
    vi.mocked(apiModule.previewTaxWorkspace).mockResolvedValue({
      tax_year: 2026,
      profile_id: "profile-1",
      profile_version: 2,
      input_snapshot: {},
      preview: {
        gross_income: "0.000",
        total_exemptions: "9000.000",
        taxable_income: "0.000",
        tax_liability: "0.000",
        total_tax_withheld: "0.000",
        net_tax_due: "0.000",
        refund_due: "0.000",
        ruleset_id: "bayyan-demo-legacy-v1",
        official_filing: false,
      },
      latest_run: null,
    });

    wrap(<TaxYearSummary />);

    await waitFor(() => {
      expect(screen.getByTestId("zero-income-notice")).toBeTruthy();
    });

    expect(screen.getByText(/ملف بدون دخل · صفر د\.أ|Zero income profile · 0 JD/i)).toBeTruthy();
    expect(screen.getAllByText(/0 د\.أ|0 JD/).length).toBeGreaterThanOrEqual(1);
  });

  it("handles up-to-date run state (latest_run present and !stale)", async () => {
    const mockPreview: TaxWorkspacePreview = {
      tax_year: 2026,
      profile_id: "profile-1",
      profile_version: 2,
      input_snapshot: {},
      preview: {
        gross_income: "15000.000",
        total_exemptions: "9000.000",
        taxable_income: "6000.000",
        net_tax_due: "300.000",
        refund_due: "0.000",
        ruleset_id: "bayyan-demo-legacy-v1",
        official_filing: false,
      },
      latest_run: {
        id: "run-101",
        tax_profile_id: "profile-1",
        tax_year: 2026,
        profile_version: 2,
        ruleset_id: "bayyan-demo-legacy-v1",
        input_fingerprint: "abc123",
        input_snapshot: {},
        output_snapshot: {},
        created_at: "2026-09-20T14:30:00Z",
        stale: false,
      },
    };
    vi.mocked(apiModule.previewTaxWorkspace).mockResolvedValue(mockPreview);

    wrap(<TaxYearSummary />);

    await waitFor(() => {
      expect(screen.getByText(/محفوظ ومُحدّث|Up to date/i)).toBeTruthy();
    });

    expect(screen.getByText(/الاحتساب المحفوظ متطابق|Saved calculation matches/i)).toBeTruthy();
  });

  it("handles stale-run state when inputs modified after calculation run (stale === true)", async () => {
    const mockPreview: TaxWorkspacePreview = {
      tax_year: 2026,
      profile_id: "profile-1",
      profile_version: 3,
      input_snapshot: {},
      preview: {
        gross_income: "18000.000",
        total_exemptions: "9000.000",
        taxable_income: "9000.000",
        net_tax_due: "450.000",
        refund_due: "0.000",
        ruleset_id: "bayyan-demo-legacy-v1",
        official_filing: false,
      },
      latest_run: {
        id: "run-100",
        tax_profile_id: "profile-1",
        tax_year: 2026,
        profile_version: 2,
        ruleset_id: "bayyan-demo-legacy-v1",
        input_fingerprint: "prev999",
        input_snapshot: {},
        output_snapshot: {},
        created_at: "2026-09-10T12:00:00Z",
        stale: true,
      },
    };
    vi.mocked(apiModule.previewTaxWorkspace).mockResolvedValue(mockPreview);

    wrap(<TaxYearSummary />);

    await waitFor(() => {
      expect(screen.getByText(/بيانات معدّلة \(بحاجة لتحديث\)|Inputs modified \(Stale\)/i)).toBeTruthy();
    });

    // Check version difference indication
    expect(screen.getByText(/v2.*v3|v3.*v2/)).toBeTruthy();
  });

  it("handles year-switch state by selecting an alternative year", async () => {
    const { selectYearMock } = wrap(<TaxYearSummary />, {
      currentYear: 2026,
      availableYears: [2026, 2025],
    });

    await waitFor(() => {
      expect(screen.getByTestId("tax-year-summary-card")).toBeTruthy();
    });

    const select = screen.getByLabelText(/السنة الضريبية|Tax Year/i);
    expect(select).toBeTruthy();

    fireEvent.change(select, { target: { value: "2025" } });
    expect(selectYearMock).toHaveBeenCalledWith(2025);
  });

  it("returns null when no tax profile is configured", () => {
    wrap(<TaxYearSummary />, { profile: null });
    expect(screen.queryByTestId("tax-year-summary-card")).toBeNull();
  });
});
