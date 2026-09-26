// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { LanguageProvider } from "../contexts/LanguageContext";
import { getPublicCapabilities } from "../services/api";
import type { PublicCapabilities } from "../types/api";
import Pricing from "./Pricing";

vi.mock("../services/api", () => ({ getPublicCapabilities: vi.fn() }));

const capabilities: PublicCapabilities = {
  product: "BAYYAN",
  tier_changes: "admin_only",
  official_filing: false,
  legal_corpus: "demo",
  ai: { configured_providers: [], document_extraction: false, advisor: false, voice: false },
  tiers: [
    { name: "Basic", max_messages_per_month: 60, max_docs_per_month: 10, max_extractions_per_month: 10, max_advisor_runs_per_month: 5, max_voice_clips_per_month: 20, max_tokens: 1024, allowed_models: [] },
    { name: "Pro", max_messages_per_month: 200, max_docs_per_month: 50, max_extractions_per_month: 50, max_advisor_runs_per_month: 25, max_voice_clips_per_month: 80, max_tokens: 2048, allowed_models: [] },
    { name: "Premium", max_messages_per_month: 500, max_docs_per_month: 150, max_extractions_per_month: 150, max_advisor_runs_per_month: 60, max_voice_clips_per_month: 200, max_tokens: 4096, allowed_models: [] },
  ],
};

function renderPricing() {
  return render(
    <MemoryRouter>
      <LanguageProvider><Pricing /></LanguageProvider>
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.resetAllMocks();
});

describe("Pricing", () => {
  it("shows server-provided limits without invented prices or payment actions", async () => {
    vi.mocked(getPublicCapabilities).mockResolvedValue(capabilities);
    renderPricing();

    expect(await screen.findByText("10 documents / month")).toBeTruthy();
    expect(screen.getByText("50 documents / month")).toBeTruthy();
    expect(screen.getByText("25 advisor runs / month")).toBeTruthy();
    expect(screen.getByText("150 documents / month")).toBeTruthy();
    expect(screen.getAllByText("No self-service upgrade")).toHaveLength(2);
    expect(screen.queryByText(/JD \/ month/)).toBeNull();
  });

  it("does not substitute stale quotas when the backend is unavailable", async () => {
    vi.mocked(getPublicCapabilities).mockRejectedValue(new Error("offline"));
    renderPricing();

    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("50 documents / month")).toBeNull();
  });

  it("renders the Basic trial upload limit in Arabic", async () => {
    localStorage.setItem("bayyan-lang", "ar");
    vi.mocked(getPublicCapabilities).mockResolvedValue(capabilities);
    renderPricing();

    expect(await screen.findByText("10 مستندًا شهريًا")).toBeTruthy();
  });
});
