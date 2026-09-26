import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { TaxProfileContext, useAuth } from "./hooks";
import {
  calculateTaxForProfile,
  getApiErrorMessage,
  listDeductions,
  listIncomeSources,
  listTaxProfiles,
} from "../services/api";
import type {
  Deduction,
  IncomeSource,
  TaxCalculationResult,
  TaxProfile,
} from "../types/api";

export type TaxProfileSnapshot = {
  profile: TaxProfile | null;
  incomeSources: IncomeSource[];
  deductions: Deduction[];
  calculation: TaxCalculationResult | null;
  version: number;
};

export type TaxProfileContextValue = TaxProfileSnapshot & {
  currentYear: number;
  availableYears: number[];
  selectYear: (year: number) => void;
  loading: boolean;
  error: string | null;
  refreshTaxProfile: () => Promise<TaxProfileSnapshot>;
};

function emptySnapshot(version: number): TaxProfileSnapshot {
  return {
    profile: null,
    incomeSources: [],
    deductions: [],
    calculation: null,
    version,
  };
}

export function TaxProfileProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [currentYear, setCurrentYear] = useState(() => new Date().getFullYear());
  const [availableYears, setAvailableYears] = useState<number[]>(() => [new Date().getFullYear()]);
  const versionRef = useRef(0);
  const requestIdRef = useRef(0);
  const [snapshot, setSnapshot] = useState<TaxProfileSnapshot>(() =>
    emptySnapshot(0),
  );
  const [loadedScope, setLoadedScope] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    requestIdRef.current += 1;
    setLoadedScope(null);
    if (!userId) return;
    const stored = Number(localStorage.getItem(`bayyan.activeYear.${userId}`));
    if (Number.isInteger(stored) && stored >= 2000 && stored <= 2100) {
      setCurrentYear(stored);
    }
  }, [userId]);

  const selectYear = useCallback((year: number) => {
    if (!Number.isInteger(year) || year < 2000 || year > 2100 || year === currentYear) return;
    requestIdRef.current += 1;
    setLoadedScope(null);
    setCurrentYear(year);
    if (userId) localStorage.setItem(`bayyan.activeYear.${userId}`, String(year));
  }, [currentYear, userId]);

  const publishSnapshot = useCallback(
    (next: Omit<TaxProfileSnapshot, "version">): TaxProfileSnapshot => {
      const version = versionRef.current + 1;
      versionRef.current = version;
      const fullSnapshot = { ...next, version };
      setSnapshot(fullSnapshot);
      return fullSnapshot;
    },
    [],
  );

  const refreshTaxProfile = useCallback(async (): Promise<TaxProfileSnapshot> => {
    const requestId = ++requestIdRef.current;
    const scope = `${userId ?? "anonymous"}:${currentYear}`;
    const isCurrent = () => requestIdRef.current === requestId;
    if (!userId) {
      setError(null);
      setLoading(false);
      setLoadedScope(null);
      return publishSnapshot({
        profile: null,
        incomeSources: [],
        deductions: [],
        calculation: null,
      });
    }

    setLoading(true);
    setError(null);

    try {
      const profiles = await listTaxProfiles();
      if (!isCurrent()) return emptySnapshot(versionRef.current);
      setAvailableYears([...new Set([new Date().getFullYear(), ...profiles.map((item) => item.tax_year)])].sort((a, b) => b - a));
      const profile = profiles.find((item) => item.tax_year === currentYear) ?? null;

      if (!profile) {
        const nextSnapshot = publishSnapshot({
          profile: null,
          incomeSources: [],
          deductions: [],
          calculation: null,
        });
        setLoadedScope(scope);
        return nextSnapshot;
      }

      const [incomeSources, deductions, calculation] = await Promise.all([
        listIncomeSources(profile.id),
        listDeductions(profile.id),
        calculateTaxForProfile(profile.id).catch(() => null),
      ]);
      if (!isCurrent()) return emptySnapshot(versionRef.current);

      const nextSnapshot = publishSnapshot({
        profile,
        incomeSources,
        deductions,
        calculation,
      });
      setLoadedScope(scope);
      return nextSnapshot;
    } catch (err) {
      if (!isCurrent()) return emptySnapshot(versionRef.current);
      setError(getApiErrorMessage(err, "Could not load tax profile."));
      publishSnapshot({
        profile: null,
        incomeSources: [],
        deductions: [],
        calculation: null,
      });
      setLoadedScope(scope);
      throw err;
    } finally {
      if (isCurrent()) setLoading(false);
    }
  }, [currentYear, publishSnapshot, userId]);

  useEffect(() => {
    void refreshTaxProfile().catch(() => undefined);
  }, [refreshTaxProfile]);

  const shouldHideSnapshot = userId === null || loadedScope !== `${userId}:${currentYear}`;
  const visibleSnapshot = useMemo(
    () => (shouldHideSnapshot ? emptySnapshot(versionRef.current) : snapshot),
    [shouldHideSnapshot, snapshot],
  );
  const visibleLoading = loading || (userId !== null && shouldHideSnapshot);

  const value = useMemo<TaxProfileContextValue>(
    () => ({
      currentYear,
      availableYears,
      selectYear,
      ...visibleSnapshot,
      loading: visibleLoading,
      error,
      refreshTaxProfile,
    }),
    [availableYears, currentYear, error, refreshTaxProfile, selectYear, visibleLoading, visibleSnapshot],
  );

  return (
    <TaxProfileContext.Provider value={value}>
      {children}
    </TaxProfileContext.Provider>
  );
}
