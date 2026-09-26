// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import Files, { getDocumentReviewStatus } from "./Files";
import { LanguageProvider } from "../contexts/LanguageContext";
import { TaxProfileContext } from "../contexts/hooks";
import { DocumentProcessingProvider } from "../contexts/DocumentProcessingContext";
import type { TaxProfileContextValue } from "../contexts/TaxProfileContext";
import * as apiModule from "../services/api";
import type { TaxProfile, UserUsage } from "../types/api";

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    api: {
      get: vi.fn(),
      post: vi.fn(),
      delete: vi.fn(),
      put: vi.fn(),
    },
    getMyUsage: vi.fn(),
    processDocument: vi.fn(),
  };
});

vi.mock("../components/ui/document-preview-modal", () => ({
  default: ({ documentId, originalFilename, onClose }: { documentId: string; originalFilename: string; onClose: () => void }) => (
    <div data-testid="document-preview-modal">
      <span>Modal: {documentId} - {originalFilename}</span>
      <button onClick={onClose}>Close Modal</button>
    </div>
  ),
}));

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
  version: 1,
};

const defaultUsage = {
  user_id: "user-1",
  tier: "Premium",
  docs: { used: 3, limit: 150, remaining: 147 },
  messages: { used: 2, limit: 500, remaining: 498 },
  voice: { used: 0, limit: 20, remaining: 20 },
  extractions: { used: 0, limit: 50, remaining: 50 },
  advisor: { used: 0, limit: 20, remaining: 20 },
};

function renderFiles(initialEntries = ["/files"]) {
  const profileVal: TaxProfileContextValue = {
    currentYear: 2026,
    availableYears: [2026, 2025],
    selectYear: vi.fn(),
    profile: defaultProfile,
    incomeSources: [],
    deductions: [],
    calculation: null,
    version: 1,
    loading: false,
    error: null,
    refreshTaxProfile: vi.fn().mockResolvedValue(null),
  };

  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <LanguageProvider>
        <TaxProfileContext.Provider value={profileVal}>
          <DocumentProcessingProvider>
            <Files />
          </DocumentProcessingProvider>
        </TaxProfileContext.Provider>
      </LanguageProvider>
    </MemoryRouter>
  );
}

describe("getDocumentReviewStatus helper (Card G-FILES-REVIEW-STATUS01)", () => {
  it("returns processing when isProcessing is true regardless of document status", () => {
    expect(getDocumentReviewStatus({ processing_status: "pending" }, true)).toBe("processing");
    expect(getDocumentReviewStatus({ processing_status: "processed" }, true)).toBe("processing");
  });

  it("returns pending for document with processing_status = pending", () => {
    expect(getDocumentReviewStatus({ processing_status: "pending" }, false)).toBe("pending");
  });

  it("returns failed for document with processing_status = failed", () => {
    expect(getDocumentReviewStatus({ processing_status: "failed" }, false)).toBe("failed");
  });

  it("returns needs_review when processed document has needs_review: true", () => {
    const doc = {
      processing_status: "processed",
      extracted_data: { confidence: 0.55, needs_review: true },
    };
    expect(getDocumentReviewStatus(doc, false)).toBe("needs_review");
  });

  it("returns awaiting_confirmation when processed document has awaiting_confirmation: true or status", () => {
    const doc1 = {
      processing_status: "processed",
      extracted_data: { confidence: 0.9, awaiting_confirmation: true },
    };
    expect(getDocumentReviewStatus(doc1, false)).toBe("awaiting_confirmation");

    const doc2 = {
      processing_status: "processed",
      extracted_data: { confidence: 0.9, status: "awaiting_confirmation" },
    };
    expect(getDocumentReviewStatus(doc2, false)).toBe("awaiting_confirmation");
  });

  it("returns awaiting_confirmation for processed document with valid extraction and no error", () => {
    const doc = {
      processing_status: "processed",
      extracted_data: { confidence: 0.95, vendor: "Hospital", amount: 200 },
    };
    expect(getDocumentReviewStatus(doc, false)).toBe("awaiting_confirmation");
  });

  it("returns needs_review for processed document without valid extraction data", () => {
    const doc = {
      processing_status: "processed",
      extracted_data: null,
    };
    expect(getDocumentReviewStatus(doc, false)).toBe("needs_review");
  });

  it("returns confirmed when has_linked_deduction is true, taking precedence over pending/failed/stale extraction", () => {
    // 1. Pending document with linked deduction
    expect(getDocumentReviewStatus({ processing_status: "pending", has_linked_deduction: true })).toBe("confirmed");

    // 2. Failed document with linked deduction
    expect(getDocumentReviewStatus({ processing_status: "failed", has_linked_deduction: true })).toBe("confirmed");

    // 3. Processed document with error or needs_review, but has_linked_deduction is true
    expect(getDocumentReviewStatus({
      processing_status: "processed",
      extracted_data: { error: "Parse failure", needs_review: true },
      has_linked_deduction: true,
    })).toBe("confirmed");

    // 4. If has_linked_deduction is false, normal review status resolution applies
    expect(getDocumentReviewStatus({
      processing_status: "processed",
      extracted_data: { confidence: 0.95, amount: 100 },
      has_linked_deduction: false,
    })).toBe("awaiting_confirmation");
  });
});

describe("Files page review status display and filtering (Card G-FILES-REVIEW-STATUS01)", () => {
  const sampleDocuments = [
    {
      id: "doc-pending",
      original_filename: "pending_receipt.pdf",
      document_type: "receipt",
      upload_date: "2026-03-01T10:00:00Z",
      processing_status: "pending",
      extracted_data: null,
    },
    {
      id: "doc-awaiting",
      original_filename: "hospital_invoice.png",
      document_type: "receipt",
      upload_date: "2026-03-02T11:00:00Z",
      processing_status: "processed",
      extracted_data: { confidence: 0.92, awaiting_confirmation: true, amount: 250 },
    },
    {
      id: "doc-needs-review",
      original_filename: "blurry_receipt.jpg",
      document_type: "receipt",
      upload_date: "2026-03-03T12:00:00Z",
      processing_status: "processed",
      extracted_data: { confidence: 0.45, needs_review: true },
    },
    {
      id: "doc-failed",
      original_filename: "corrupt_file.pdf",
      document_type: "receipt",
      upload_date: "2026-03-04T13:00:00Z",
      processing_status: "failed",
      extracted_data: { error: "Unreadable image" },
    },
    {
      id: "doc-confirmed",
      original_filename: "confirmed_deduction.pdf",
      document_type: "receipt",
      upload_date: "2026-03-05T14:00:00Z",
      processing_status: "processed",
      extracted_data: { confidence: 0.95, amount: 300 },
      has_linked_deduction: true,
    },
  ];

  beforeEach(() => {
    vi.mocked(apiModule.getMyUsage).mockResolvedValue(defaultUsage as unknown as UserUsage);
    vi.mocked(apiModule.api.get).mockResolvedValue({ data: sampleDocuments });
  });

  it("renders documents with their respective review status chips", async () => {
    renderFiles();

    await waitFor(() => {
      expect(screen.getByText("pending_receipt.pdf")).toBeTruthy();
    });

    expect(screen.getByText("hospital_invoice.png")).toBeTruthy();
    expect(screen.getByText("blurry_receipt.jpg")).toBeTruthy();
    expect(screen.getByText("corrupt_file.pdf")).toBeTruthy();

    // Check review status indicators rendered via data-testid
    const pendingChip = screen.getByTestId("review-status-doc-pending");
    expect(pendingChip.textContent).toMatch(/Pending Extraction/i);

    const awaitingChip = screen.getByTestId("review-status-doc-awaiting");
    expect(awaitingChip.textContent).toMatch(/Awaiting Confirmation/i);

    const needsReviewChip = screen.getByTestId("review-status-doc-needs-review");
    expect(needsReviewChip.textContent).toMatch(/Needs Review/i);

    const failedChip = screen.getByTestId("review-status-doc-failed");
    expect(failedChip.textContent).toMatch(/Failed/i);

    const confirmedChip = screen.getByTestId("review-status-doc-confirmed");
    expect(confirmedChip.textContent).toMatch(/Confirmed/i);
  });

  it("filters documents client-side by review_status without sending invalid params to backend", async () => {
    // Initial route has review_status=awaiting_confirmation
    renderFiles(["/files?review_status=awaiting_confirmation"]);

    await waitFor(() => {
      expect(screen.getByText("hospital_invoice.png")).toBeTruthy();
    });

    // Only awaiting confirmation document should be visible
    expect(screen.queryByText("pending_receipt.pdf")).toBeNull();
    expect(screen.queryByText("blurry_receipt.jpg")).toBeNull();
    expect(screen.queryByText("corrupt_file.pdf")).toBeNull();

    // Verify backend call params did NOT include review_status
    expect(apiModule.api.get).toHaveBeenCalledWith("/documents", {
      params: {},
    });
  });

  it("filters documents by needs_review when clicked", async () => {
    renderFiles();

    await waitFor(() => {
      expect(screen.getByText("pending_receipt.pdf")).toBeTruthy();
    });

    // Find filter button for Needs Review
    const needsReviewFilterBtn = screen.getByRole("button", { name: /^Needs Review$/i });
    fireEvent.click(needsReviewFilterBtn);

    await waitFor(() => {
      expect(screen.getByText("blurry_receipt.jpg")).toBeTruthy();
    });

    expect(screen.queryByText("pending_receipt.pdf")).toBeNull();
    expect(screen.queryByText("hospital_invoice.png")).toBeNull();
    expect(screen.queryByText("corrupt_file.pdf")).toBeNull();
  });

  it("opens DocumentPreviewModal when Review button is clicked", async () => {
    renderFiles();

    await waitFor(() => {
      expect(screen.getByText("hospital_invoice.png")).toBeTruthy();
    });

    const reviewBtn = screen.getByRole("button", { name: "Review: hospital_invoice.png" });
    fireEvent.click(reviewBtn);

    await waitFor(() => {
      expect(screen.getByTestId("document-preview-modal")).toBeTruthy();
    });

    expect(screen.getByText(/Modal: doc-awaiting - hospital_invoice.png/i)).toBeTruthy();

    // Close modal
    fireEvent.click(screen.getByText("Close Modal"));

    await waitFor(() => {
      expect(screen.queryByTestId("document-preview-modal")).toBeNull();
    });
  });

  it("filters documents by confirmed review status when clicked", async () => {
    renderFiles();

    await waitFor(() => {
      expect(screen.getByText("confirmed_deduction.pdf")).toBeTruthy();
    });

    const confirmedFilterBtn = screen.getByRole("button", { name: /^Confirmed$/i });
    fireEvent.click(confirmedFilterBtn);

    await waitFor(() => {
      expect(screen.getByText("confirmed_deduction.pdf")).toBeTruthy();
    });

    expect(screen.queryByText("pending_receipt.pdf")).toBeNull();
    expect(screen.queryByText("hospital_invoice.png")).toBeNull();
    expect(screen.queryByText("blurry_receipt.jpg")).toBeNull();
    expect(screen.queryByText("corrupt_file.pdf")).toBeNull();
  });
});
