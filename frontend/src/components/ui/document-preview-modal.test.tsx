// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../../contexts/LanguageContext";
import { TaxProfileContext } from "../../contexts/hooks";
import type { TaxProfileContextValue } from "../../contexts/TaxProfileContext";
import * as apiModule from "../../services/api";
import DocumentPreviewModal from "./document-preview-modal";
import type { Deduction, ExtractionDebugResult, TaxProfile } from "../../types/api";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../services/api")>();
  return {
    ...actual,
    getDocumentPreviewBlob: vi.fn(),
    getExtractionDebug: vi.fn(),
    createDeduction: vi.fn(),
  };
});

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.clearAllMocks();
});

const defaultProfile: TaxProfile = {
  id: "profile-1",
  user_id: "user-1",
  tax_year: 2026,
  residency_status: "resident",
  marital_status: "single",
  num_dependents: 0,
  filing_status: "individual",
  claims_dependents_exemption: false,
  claim_spouse_expense_exemption: false,
  disability_exemption_count: 0,
  created_at: "2026-01-01T00:00:00Z",
  version: 3,
};

function wrap(ui: React.ReactElement, mockProfileValue?: Partial<TaxProfileContextValue>) {
  const profileVal: TaxProfileContextValue = {
    currentYear: 2026,
    availableYears: [2026, 2025],
    selectYear: vi.fn(),
    profile: defaultProfile,
    incomeSources: [],
    deductions: [],
    calculation: null,
    version: 3,
    loading: false,
    error: null,
    refreshTaxProfile: vi.fn().mockResolvedValue({
      profile: defaultProfile,
      incomeSources: [],
      deductions: [],
      calculation: null,
      version: 4,
    }),
    ...mockProfileValue,
  };

  return render(
    <MemoryRouter>
      <LanguageProvider>
        <TaxProfileContext.Provider value={profileVal}>{ui}</TaxProfileContext.Provider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

describe("DocumentPreviewModal review & verification flow (Card G-DOC-REVIEW01)", () => {
  beforeEach(() => {
    // Mock blob preview as fake image
    const fakeBlob = new Blob(["fake-image-bytes"], { type: "image/png" });
    vi.mocked(apiModule.getDocumentPreviewBlob).mockResolvedValue(fakeBlob);
    // Mock URL.createObjectURL and URL.revokeObjectURL
    globalThis.URL.createObjectURL = vi.fn(() => "blob:http://localhost/fake-image");
    globalThis.URL.revokeObjectURL = vi.fn();
  });

  it("handles pending document: shows pending status, routing hint, and manual entry path", async () => {
    const pendingFixture: ExtractionDebugResult = {
      document_id: "doc-pending-1",
      original_filename: "receipt_pending.png",
      document_type: "receipt",
      processing_status: "pending",
      upload_date: "2026-02-15T10:00:00Z",
      extracted_data: null,
      deduction: null,
    };
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(pendingFixture);

    wrap(
      <DocumentPreviewModal
        documentId="doc-pending-1"
        originalFilename="receipt_pending.png"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/pending/i)).toBeTruthy();
    });

    // Check routing hint
    expect(screen.getAllByText(/Pending extraction/i).length).toBeGreaterThanOrEqual(1);
    // Manual review card is available
    expect(screen.getByTestId("manual-review-card")).toBeTruthy();
  });

  it("handles high-confidence processed document: renders confidence, fields, and routing hint", async () => {
    const processedFixture: ExtractionDebugResult = {
      document_id: "doc-processed-1",
      original_filename: "hospital_invoice.png",
      document_type: "receipt",
      processing_status: "processed",
      upload_date: "2026-03-01T12:00:00Z",
      extracted_data: {
        vendor: "Amman Specialty Hospital",
        amount: 320.5,
        date: "2026-03-01",
        category: "medical",
        document_type: "receipt",
        confidence: 0.94,
        extractor_backend: "gemini-2.5-flash",
      },
      deduction: null,
    };
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(processedFixture);

    wrap(
      <DocumentPreviewModal
        documentId="doc-processed-1"
        originalFilename="hospital_invoice.png"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/processed/i)).toBeTruthy();
    });

    expect(screen.getByText("94%")).toBeTruthy();
    expect(screen.getByText(/High confidence/i)).toBeTruthy();
    expect(screen.getByText("Amman Specialty Hospital")).toBeTruthy();
    expect(screen.getByText("320.50")).toBeTruthy();
  });

  it("handles low-confidence document with needs_review: shows review warning routing hint", async () => {
    const lowConfFixture: ExtractionDebugResult = {
      document_id: "doc-low-1",
      original_filename: "crumpled_receipt.png",
      document_type: "receipt",
      processing_status: "processed",
      upload_date: "2026-03-02T14:00:00Z",
      extracted_data: {
        vendor: "Corner Pharmacy",
        amount: 45.0,
        date: "2026-03-02",
        category: "medical",
        document_type: "receipt",
        confidence: 0.62,
        needs_review: true,
        extractor_backend: "gemini-2.5-flash",
      },
      deduction: null,
    };
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(lowConfFixture);

    wrap(
      <DocumentPreviewModal
        documentId="doc-low-1"
        originalFilename="crumpled_receipt.png"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/processed/i)).toBeTruthy();
    });

    expect(screen.getByText("62%")).toBeTruthy();
    expect(screen.getByText(/Review needed/i)).toBeTruthy();
    expect(screen.getByTestId("manual-review-card")).toBeTruthy();
  });

  it("detects and flags tax year mismatch visibly", async () => {
    // Profile is year 2026, document extracted date is in 2024
    const mismatchFixture: ExtractionDebugResult = {
      document_id: "doc-mismatch-1",
      original_filename: "old_tuition_2024.png",
      document_type: "receipt",
      processing_status: "processed",
      upload_date: "2026-03-05T09:00:00Z",
      extracted_data: {
        vendor: "Modern Academy School",
        amount: 800.0,
        date: "2024-09-15",
        category: "education",
        document_type: "receipt",
        confidence: 0.91,
        extractor_backend: "gemini-2.5-flash",
      },
      deduction: null,
    };
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(mismatchFixture);

    wrap(
      <DocumentPreviewModal
        documentId="doc-mismatch-1"
        originalFilename="old_tuition_2024.png"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("year-mismatch-warning")).toBeTruthy();
    });

    const warningText = screen.getByTestId("year-mismatch-warning").textContent;
    expect(warningText).toContain("2024");
    expect(warningText).toContain("2026");
  });

  it("displays existing linked deduction and prevents redundant addition", async () => {
    const linkedFixture: ExtractionDebugResult = {
      document_id: "doc-linked-1",
      original_filename: "verified_medical.png",
      document_type: "receipt",
      processing_status: "processed",
      upload_date: "2026-03-01T10:00:00Z",
      extracted_data: {
        vendor: "Amman Dental Clinic",
        amount: 175.0,
        date: "2026-02-20",
        category: "medical",
        confidence: 0.95,
        extractor_backend: "gemini-2.5-flash",
      },
      deduction: {
        id: "ded-existing-1",
        tax_profile_id: "profile-1",
        category: "medical",
        amount: 175.0,
        date: "2026-02-20",
        description: "Amman Dental Clinic",
        beneficiary: "self",
        beneficiary_name: null,
        document_id: "doc-linked-1",
      },
    };
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(linkedFixture);

    wrap(
      <DocumentPreviewModal
        documentId="doc-linked-1"
        originalFilename="verified_medical.png"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/✓ Deduction created/i)).toBeTruthy();
    });

    expect(screen.getByText(/175.00 JD/i)).toBeTruthy();
    // Manual review card should not be present since deduction is already created
    expect(screen.queryByTestId("manual-review-card")).toBeNull();
  });

  it("allows explicit user confirmation to create deduction via safe API with version check", async () => {
    const unlinkedFixture: ExtractionDebugResult = {
      document_id: "doc-confirm-1",
      original_filename: "school_fees.png",
      document_type: "receipt",
      processing_status: "processed",
      upload_date: "2026-03-01T10:00:00Z",
      extracted_data: {
        vendor: "International School",
        amount: 450.0,
        date: "2026-02-10",
        category: "education",
        confidence: 0.88,
        extractor_backend: "gemini-2.5-flash",
      },
      deduction: null,
    };
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(unlinkedFixture);
    vi.mocked(apiModule.createDeduction).mockResolvedValue({
      id: "new-ded-123",
      tax_profile_id: "profile-1",
      category: "education",
      amount: 450.0,
      date: "2026-02-10",
      description: "International School",
      beneficiary: "self",
      beneficiary_name: null,
      document_id: "doc-confirm-1",
    });

    wrap(
      <DocumentPreviewModal
        documentId="doc-confirm-1"
        originalFilename="school_fees.png"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId("manual-review-card")).toBeTruthy();
    });

    // Toggle open the form if closed
    const openBtn = screen.queryByRole("button", { name: /Enter \/ Confirm as Tax Deduction/i });
    if (openBtn) {
      fireEvent.click(openBtn);
    }

    const confirmBtn = screen.getByRole("button", { name: /Confirm and Add to Tax Deductions/i });
    expect(confirmBtn).toBeTruthy();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);
    });

    expect(apiModule.createDeduction).toHaveBeenCalledWith(
      expect.objectContaining({
        tax_profile_id: "profile-1",
        category: "education",
        amount: 450,
        date: "2026-02-10",
        description: "International School",
        document_id: "doc-confirm-1",
      }),
      3 // Expected version from taxProfile.version
    );

    // Verify success message displayed
    await waitFor(() => {
      expect(screen.getByText(/Deduction successfully added/i)).toBeTruthy();
    });
  });
});

// ── Card C-DOC-TEST01 — manual deduction card guards ─────────────────────────

// A processed receipt with extraction data but no linked deduction yet, so the
// manual deduction card (ManualReviewCard) renders.
const unlinkedReceiptFixture: ExtractionDebugResult = {
  document_id: "doc-confirm-1",
  original_filename: "school_fees.png",
  document_type: "receipt",
  processing_status: "processed",
  upload_date: "2026-03-01T10:00:00Z",
  extracted_data: {
    vendor: "International School",
    amount: 450.0,
    date: "2026-02-10",
    category: "education",
    confidence: 0.88,
    extractor_backend: "gemini-2.5-flash",
  },
  deduction: null,
};

function createdDeduction(): Deduction {
  return {
    id: "new-ded-456",
    tax_profile_id: "profile-1",
    category: "education",
    amount: 450.0,
    date: "2026-02-10",
    description: "International School",
    beneficiary: "self",
    beneficiary_name: null,
    document_id: "doc-confirm-1",
  };
}

// Shaped like an axios error so the real `getApiErrorMessage` helper (spread
// through the module mock) reads `response.data.detail`, and so the conflict
// branch in the component can read `response.status`.
function apiError(status: number, detail: string) {
  return { isAxiosError: true, response: { status, data: { detail } } };
}

function okRefreshResult() {
  return {
    profile: defaultProfile,
    incomeSources: [],
    deductions: [],
    calculation: null,
    version: 4,
  };
}

// Opens the manual entry form and returns the confirm button element. The
// element reference stays valid while React swaps its label and disabled state.
async function openManualForm(): Promise<HTMLButtonElement> {
  await waitFor(() => {
    expect(screen.getByTestId("manual-review-card")).toBeTruthy();
  });
  const openBtn = screen.queryByRole("button", {
    name: /Enter \/ Confirm as Tax Deduction/i,
  });
  if (openBtn) fireEvent.click(openBtn);
  return screen.getByRole("button", {
    name: /Confirm and Add to Tax Deductions/i,
  }) as HTMLButtonElement;
}

describe("DocumentPreviewModal manual deduction card guards (Card C-DOC-TEST01)", () => {
  beforeEach(() => {
    const fakeBlob = new Blob(["fake-image-bytes"], { type: "image/png" });
    vi.mocked(apiModule.getDocumentPreviewBlob).mockResolvedValue(fakeBlob);
    globalThis.URL.createObjectURL = vi.fn(() => "blob:http://localhost/fake-image");
    globalThis.URL.revokeObjectURL = vi.fn();
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(unlinkedReceiptFixture);
  });

  it("keeps a rapid double confirmation to exactly one createDeduction call", async () => {
    // The first save stays in flight while the second confirmation arrives —
    // the race that could otherwise create a duplicate deduction for the same
    // document (the server also rejects duplicates via migration 018).
    let finishCreate: () => void = () => undefined;
    const slowCreate = new Promise<Deduction>((resolve) => {
      finishCreate = () => resolve(createdDeduction());
    });
    vi.mocked(apiModule.createDeduction).mockImplementation(() => slowCreate);

    wrap(
      <DocumentPreviewModal
        documentId="doc-confirm-1"
        originalFilename="school_fees.png"
        onClose={vi.fn()}
      />
    );
    const confirmBtn = await openManualForm();

    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);

    expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);
    // The confirm control is inert for the duration of the in-flight save.
    expect(confirmBtn.disabled).toBe(true);

    finishCreate();
    await waitFor(() => {
      expect(screen.getByText(/Deduction successfully added/i)).toBeTruthy();
    });
    expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);
  });
  it("ignores a second confirmation that reaches the form while a save is in flight", async () => {
    // A rapid second confirmation can arrive as a raw submit (for example
    // pressing Enter in the amount field) before React re-renders the button as
    // disabled, so the handler itself — not only the button attribute — has to
    // be safe against re-entry.
    let finishCreate: () => void = () => undefined;
    const slowCreate = new Promise<Deduction>((resolve) => {
      finishCreate = () => resolve(createdDeduction());
    });
    vi.mocked(apiModule.createDeduction).mockImplementation(() => slowCreate);

    wrap(
      <DocumentPreviewModal
        documentId="doc-confirm-1"
        originalFilename="school_fees.png"
        onClose={vi.fn()}
      />
    );
    const confirmBtn = await openManualForm();
    const form = confirmBtn.closest("form") as HTMLFormElement;
    expect(form).toBeTruthy();

    fireEvent.submit(form);
    fireEvent.submit(form);

    expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);

    finishCreate();
    await waitFor(() => {
      expect(screen.getByText(/Deduction successfully added/i)).toBeTruthy();
    });
    expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);
  });



  it("surfaces a stale profile version conflict (409) instead of a false success", async () => {
    const refreshTaxProfile = vi.fn().mockResolvedValue(okRefreshResult());
    vi.mocked(apiModule.createDeduction).mockRejectedValue(
      apiError(409, "Tax profile was modified by another change. Reload and try again.")
    );

    wrap(
      <DocumentPreviewModal
        documentId="doc-confirm-1"
        originalFilename="school_fees.png"
        onClose={vi.fn()}
      />,
      { refreshTaxProfile }
    );
    const confirmBtn = await openManualForm();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Tax profile was modified by another change/i)
      ).toBeTruthy();
    });

    // A rejected write must never look like a saved deduction.
    expect(screen.queryByText(/Deduction successfully added/i)).toBeNull();
    expect(screen.getByTestId("manual-review-card")).toBeTruthy();

    // The write still carries the document linkage and the If-Match version.
    expect(apiModule.createDeduction).toHaveBeenCalledWith(
      expect.objectContaining({
        tax_profile_id: "profile-1",
        document_id: "doc-confirm-1",
        amount: 450,
      }),
      3
    );

    // A 409 means the version we sent is stale, so the profile is resynced —
    // otherwise every retry would replay the same rejected version.
    await waitFor(() => {
      expect(refreshTaxProfile).toHaveBeenCalled();
    });

    // And the taxpayer can confirm again.
    await waitFor(() => {
      expect(confirmBtn.disabled).toBe(false);
    });
  });

  it("allows a retry after a failed save and succeeds on the second attempt", async () => {
    const refreshTaxProfile = vi.fn().mockResolvedValue(okRefreshResult());
    vi.mocked(apiModule.createDeduction)
      .mockRejectedValueOnce(apiError(500, "Unexpected server error"))
      .mockResolvedValueOnce(createdDeduction());

    wrap(
      <DocumentPreviewModal
        documentId="doc-confirm-1"
        originalFilename="school_fees.png"
        onClose={vi.fn()}
      />,
      { refreshTaxProfile }
    );
    const confirmBtn = await openManualForm();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/Unexpected server error/i)).toBeTruthy();
    });
    expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);

    // The guard must release on failure, not latch the control shut.
    await waitFor(() => {
      expect(confirmBtn.disabled).toBe(false);
    });

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/Deduction successfully added/i)).toBeTruthy();
    });
    expect(apiModule.createDeduction).toHaveBeenCalledTimes(2);
    expect(apiModule.createDeduction).toHaveBeenLastCalledWith(
      expect.objectContaining({
        tax_profile_id: "profile-1",
        document_id: "doc-confirm-1",
        amount: 450,
      }),
      3
    );
  });
});

// ── Card C-DOC-TEST01b — post-create refresh/reload failures ─────────────────

const MODAL_PROPS = {
  documentId: "doc-confirm-1",
  originalFilename: "school_fees.png",
};

function modalContextValue(
  version: number,
  profileValue: Partial<TaxProfileContextValue>
): TaxProfileContextValue {
  return {
    currentYear: 2026,
    availableYears: [2026, 2025],
    selectYear: vi.fn(),
    profile: { ...defaultProfile, version },
    incomeSources: [],
    deductions: [],
    calculation: null,
    version,
    loading: false,
    error: null,
    refreshTaxProfile: vi.fn().mockResolvedValue(okRefreshResult()),
    ...profileValue,
  };
}

// Renders the modal at an explicit profile version so a test can model the app
// re-rendering with the refreshed version after a conflict.
function modalTree(
  version: number,
  profileValue: Partial<TaxProfileContextValue> = {}
): React.ReactElement {
  return (
    <MemoryRouter>
      <LanguageProvider>
        <TaxProfileContext.Provider value={modalContextValue(version, profileValue)}>
          <DocumentPreviewModal {...MODAL_PROPS} onClose={vi.fn()} />
        </TaxProfileContext.Provider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

describe("DocumentPreviewModal post-create follow-up failures (Card C-DOC-TEST01b)", () => {
  beforeEach(() => {
    const fakeBlob = new Blob(["fake-image-bytes"], { type: "image/png" });
    vi.mocked(apiModule.getDocumentPreviewBlob).mockResolvedValue(fakeBlob);
    globalThis.URL.createObjectURL = vi.fn(() => "blob:http://localhost/fake-image");
    globalThis.URL.revokeObjectURL = vi.fn();
    vi.mocked(apiModule.getExtractionDebug).mockResolvedValue(unlinkedReceiptFixture);
  });

  it("shows document review controls and the unlinked state in Arabic", async () => {
    localStorage.setItem("bayyan-lang", "ar");
    wrap(<DocumentPreviewModal {...MODAL_PROPS} onClose={vi.fn()} />);

    expect(await screen.findByText("مراجعة المستند والتحقق الضريبي")).toBeTruthy();
    expect(screen.getByRole("button", { name: "إغلاق معاينة المستند" })).toBeTruthy();
    expect(screen.getByText("لم يُنشأ اقتطاع بعد")).toBeTruthy();
    expect(screen.getByText("الإدخال والتحقق اليدوي")).toBeTruthy();
  });

  it("reports the save as successful when the follow-up profile refresh fails", async () => {
    // The POST succeeds but the follow-up read does not. A fresh read is not
    // part of the write, so the taxpayer must not be told the save failed.
    const refreshTaxProfile = vi
      .fn()
      .mockRejectedValue(new Error("profile refresh failed"));
    vi.mocked(apiModule.createDeduction).mockResolvedValue(createdDeduction());

    wrap(<DocumentPreviewModal {...MODAL_PROPS} onClose={vi.fn()} />, { refreshTaxProfile });
    const confirmBtn = await openManualForm();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/Deduction successfully added/i)).toBeTruthy();
    });

    expect(screen.queryByText(/Failed to create deduction/i)).toBeNull();
    expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);
  });

  it("does not send a second POST after a successful create when the debug reload fails", async () => {
    // The deduction is created, but reloading the extraction details fails, so
    // the manual card stays on screen and the taxpayer could confirm again.
    vi.mocked(apiModule.getExtractionDebug)
      .mockResolvedValueOnce(unlinkedReceiptFixture)
      .mockRejectedValueOnce(apiError(500, "extraction reload failed"));
    vi.mocked(apiModule.createDeduction).mockResolvedValue(createdDeduction());

    wrap(<DocumentPreviewModal {...MODAL_PROPS} onClose={vi.fn()} />);
    const confirmBtn = await openManualForm();

    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(screen.getByText(/Deduction successfully added/i)).toBeTruthy();
    });

    // The card is still mounted because the reload failed.
    expect(screen.getByTestId("manual-review-card")).toBeTruthy();
    expect(confirmBtn).toHaveProperty("disabled", true);

    // Even a raw form submit after save cannot post the document twice.
    fireEvent.submit(confirmBtn.closest("form")!);
    expect(apiModule.createDeduction).toHaveBeenCalledTimes(1);
  });

  it("retries a 409 conflict with the refreshed profile version", async () => {
    const refreshTaxProfile = vi.fn().mockResolvedValue(okRefreshResult());
    vi.mocked(apiModule.createDeduction)
      .mockRejectedValueOnce(apiError(409, "Tax profile was modified by another change."))
      .mockResolvedValueOnce(createdDeduction());

    const view = render(modalTree(3, { refreshTaxProfile }));
    const confirmBtn = await openManualForm();

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/modified by another change/i)).toBeTruthy();
    });
    // First attempt carried the version we had.
    expect(apiModule.createDeduction).toHaveBeenCalledWith(
      expect.objectContaining({ document_id: "doc-confirm-1" }),
      3
    );
    await waitFor(() => {
      expect(refreshTaxProfile).toHaveBeenCalled();
    });

    // The refreshed profile lands in context (version 3 -> 4).
    view.rerender(modalTree(4, { refreshTaxProfile }));

    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(screen.getByText(/Deduction successfully added/i)).toBeTruthy();
    });
    // The retry must send the refreshed version, not replay the rejected one.
    expect(apiModule.createDeduction).toHaveBeenLastCalledWith(
      expect.objectContaining({ document_id: "doc-confirm-1" }),
      4
    );
    expect(apiModule.createDeduction).toHaveBeenCalledTimes(2);
  });
});
