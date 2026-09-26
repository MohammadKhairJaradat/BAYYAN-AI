import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  getLatestAdvisorReport,
  runAdvisor as apiRunAdvisor,
} from "../services/api";
import type { AdvisorLang, AdvisorReport, TaxProfile } from "../types/api";
import { AdvisorContext, useAuth, useTaxProfile } from "./hooks";

const STORAGE_KEY = "taxai.advisorState";
const STALE_PROFILE_VERSION = -1;

export type AdvisorPhase =
  | "loading"
  | "bootstrap"
  | "ready"
  | "running"
  | "report"
  | "error";

interface PersistedState {
  phase: AdvisorPhase;
  report: AdvisorReport | null;
  errorMsg: string | null;
  reportProfileVersion: number | null;
  lang: AdvisorLang;
}

const INITIAL_STATE: PersistedState = {
  phase: "loading",
  report: null,
  errorMsg: null,
  reportProfileVersion: null,
  lang: "ar",
};

function hydrateFromStorage(): PersistedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return INITIAL_STATE;
    const parsed = JSON.parse(raw) as Partial<PersistedState>;
    const next: PersistedState = {
      phase: parsed.phase ?? INITIAL_STATE.phase,
      report: parsed.report ?? null,
      errorMsg: parsed.errorMsg ?? null,
      reportProfileVersion: parsed.reportProfileVersion ?? null,
      lang: parsed.lang ?? INITIAL_STATE.lang,
    };
    // The in-flight promise died with the page. Fall back to the previous
    // report if we have one (staleness banner still flags it); otherwise
    // drop to "ready" so the user can click Run again instead of staring
    // at a phantom spinner.
    if (next.phase === "running") {
      next.phase = next.report ? "report" : "ready";
    }
    return next;
  } catch {
    return INITIAL_STATE;
  }
}

export interface AdvisorContextValue {
  phase: AdvisorPhase;
  report: AdvisorReport | null;
  errorMsg: string | null;
  reportProfileVersion: number | null;
  lang: AdvisorLang;

  setPhase: (
    next: AdvisorPhase | ((prev: AdvisorPhase) => AdvisorPhase),
  ) => void;
  setLang: (next: AdvisorLang) => void;
  setErrorMsg: (msg: string | null) => void;
  runAnalysis: (
    profile: TaxProfile,
    runLang: AdvisorLang,
    profileVersion: number,
    errorMessage: string,
  ) => Promise<void>;
  reset: () => void;
}

export function AdvisorProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const {
    profile,
    loading: profileLoading,
    version: taxProfileVersion,
  } = useTaxProfile();
  const userId = user?.id ?? null;
  const profileId = profile?.id ?? null;
  const [state, setState] = useState<PersistedState>(() =>
    hydrateFromStorage(),
  );
  const runIdRef = useRef(0);
  const latestLoadedProfileIdRef = useRef<string | null>(null);
  const latestRequestIdRef = useRef(0);

  useEffect(() => {
    if (state.phase === "loading") return;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* quota / private mode — ignore */
    }
  }, [state]);

  useEffect(() => {
    if (!userId || profileLoading || !profileId) {
      latestRequestIdRef.current += 1;
      if (profileLoading || !profileId) latestLoadedProfileIdRef.current = null;
      return;
    }
    if (latestLoadedProfileIdRef.current === profileId) return;

    latestLoadedProfileIdRef.current = profileId;
    const requestId = ++latestRequestIdRef.current;

    void (async () => {
      try {
        const latest = await getLatestAdvisorReport(profileId);
        if (latestRequestIdRef.current !== requestId) return;

        if (!latest) {
          setState((prev) =>
            prev.phase === "loading" ? { ...prev, phase: "ready" } : prev,
          );
          return;
        }

        setState((prev) => {
          if (prev.phase === "running") return prev;
          return {
            ...prev,
            phase: "report",
            report: latest.report,
            errorMsg: null,
            lang: latest.report.lang,
            reportProfileVersion: latest.is_stale
              ? STALE_PROFILE_VERSION
              : taxProfileVersion,
          };
        });
      } catch {
        // Keep localStorage-hydrated state if the latest-report fetch fails.
      }
    })();
  }, [profileId, profileLoading, taxProfileVersion, userId]);

  const setPhase = useCallback(
    (next: AdvisorPhase | ((prev: AdvisorPhase) => AdvisorPhase)) => {
      setState((prev) => {
        const nextPhase =
          typeof next === "function" ? next(prev.phase) : next;
        if (nextPhase === prev.phase) return prev;
        return { ...prev, phase: nextPhase };
      });
    },
    [],
  );

  const setLang = useCallback((next: AdvisorLang) => {
    setState((prev) => (prev.lang === next ? prev : { ...prev, lang: next }));
  }, []);

  const setErrorMsg = useCallback((msg: string | null) => {
    setState((prev) =>
      prev.errorMsg === msg ? prev : { ...prev, errorMsg: msg },
    );
  }, []);

  const runAnalysis = useCallback(
    async (
      profile: TaxProfile,
      runLang: AdvisorLang,
      profileVersion: number,
      errorMessage: string,
    ) => {
      const myRunId = ++runIdRef.current;
      setState((prev) => ({ ...prev, phase: "running", errorMsg: null }));
      try {
        const r = await apiRunAdvisor(profile.id, runLang);
        if (runIdRef.current !== myRunId) return;
        setState((prev) => ({
          ...prev,
          report: r,
          reportProfileVersion: profileVersion,
          phase: "report",
          errorMsg: null,
        }));
      } catch {
        if (runIdRef.current !== myRunId) return;
        setState((prev) => ({
          ...prev,
          phase: "error",
          errorMsg: errorMessage,
        }));
      }
    },
    [],
  );

  const reset = useCallback(() => {
    runIdRef.current += 1;
    setState(INITIAL_STATE);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  const value: AdvisorContextValue = {
    phase: state.phase,
    report: state.report,
    errorMsg: state.errorMsg,
    reportProfileVersion: state.reportProfileVersion,
    lang: state.lang,
    setPhase,
    setLang,
    setErrorMsg,
    runAnalysis,
    reset,
  };

  return (
    <AdvisorContext.Provider value={value}>{children}</AdvisorContext.Provider>
  );
}
