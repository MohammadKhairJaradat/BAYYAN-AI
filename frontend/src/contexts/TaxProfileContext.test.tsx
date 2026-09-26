// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { calculateTaxForProfile, listDeductions, listIncomeSources, listTaxProfiles } from "../services/api";
import type { IncomeSource, TaxCalculationResult, TaxProfile, User } from "../types/api";
import type { AuthContextType } from "./AuthContext";
import { TaxProfileProvider } from "./TaxProfileContext";
import { AuthContext, useTaxProfile } from "./hooks";

vi.mock("../services/api", () => ({
  calculateTaxForProfile: vi.fn(), listDeductions: vi.fn(),
  listIncomeSources: vi.fn(), listTaxProfiles: vi.fn(),
}));

function Probe({ previousYear }: { previousYear: number }) {
  const { currentYear, profile, loading, selectYear } = useTaxProfile();
  return <div>
    <span data-testid="scope">{currentYear}:{profile?.id ?? "none"}:{loading ? "loading" : "ready"}</span>
    <button onClick={() => selectYear(previousYear)}>Older year</button>
  </div>;
}

afterEach(() => { cleanup(); localStorage.clear(); vi.resetAllMocks(); });

it("isolates year loads and ignores an older response that finishes last", async () => {
  const currentYear = new Date().getFullYear();
  const previousYear = currentYear - 1;
  const profiles = [
    { id: "current", tax_year: currentYear },
    { id: "previous", tax_year: previousYear },
  ] as TaxProfile[];
  let releaseCurrent: (rows: IncomeSource[]) => void = () => undefined;
  const slowCurrent = new Promise<IncomeSource[]>((resolve) => { releaseCurrent = resolve; });
  vi.mocked(listTaxProfiles).mockResolvedValue(profiles);
  vi.mocked(listIncomeSources).mockImplementation((id) => id === "current" ? slowCurrent : Promise.resolve([]));
  vi.mocked(listDeductions).mockResolvedValue([]);
  vi.mocked(calculateTaxForProfile).mockResolvedValue({} as TaxCalculationResult);

  const auth = { user: { id: "user-a" } as User, loading: false } as AuthContextType;
  render(<AuthContext.Provider value={auth}><TaxProfileProvider><Probe previousYear={previousYear} /></TaxProfileProvider></AuthContext.Provider>);
  await waitFor(() => expect(listIncomeSources).toHaveBeenCalledWith("current"));
  fireEvent.click(screen.getByText("Older year"));
  expect(screen.getByTestId("scope").textContent).toBe(`${previousYear}:none:loading`);
  await waitFor(() => expect(screen.getByTestId("scope").textContent).toBe(`${previousYear}:previous:ready`));
  releaseCurrent([]);
  await waitFor(() => expect(screen.getByTestId("scope").textContent).toBe(`${previousYear}:previous:ready`));
  expect(localStorage.getItem("bayyan.activeYear.user-a")).toBe(String(previousYear));
});
