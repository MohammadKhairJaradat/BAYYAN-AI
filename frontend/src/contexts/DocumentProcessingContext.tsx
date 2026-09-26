import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { processDocument, type ProcessDocumentResult } from "../services/api";
import { DocumentProcessingContext } from "./hooks";

const STORAGE_KEY = "taxai.documentProcessingState";

interface BulkProgress {
  total: number;
  completed: number;
  errorCount: number;
}

interface PersistedState {
  processingIds: string[];
  bulkProgress: BulkProgress | null;
  isBulkProcessing: boolean;
  lastUpdatedAt: number;
}

const INITIAL_STATE: PersistedState = {
  processingIds: [],
  bulkProgress: null,
  isBulkProcessing: false,
  lastUpdatedAt: 0,
};

function hydrateFromStorage(): PersistedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return INITIAL_STATE;
    const parsed = JSON.parse(raw) as Partial<PersistedState>;
    const next: PersistedState = {
      processingIds: Array.isArray(parsed.processingIds) ? parsed.processingIds : [],
      bulkProgress: parsed.bulkProgress ?? null,
      isBulkProcessing: parsed.isBulkProcessing ?? false,
      lastUpdatedAt: parsed.lastUpdatedAt ?? 0,
    };
    // Promises die with the page. If we saw activity in storage, the
    // backend may have completed it while we were gone — drop the spinner
    // state but bump lastUpdatedAt so listeners refetch and reconcile.
    if (next.processingIds.length > 0 || next.isBulkProcessing) {
      return {
        processingIds: [],
        bulkProgress: null,
        isBulkProcessing: false,
        lastUpdatedAt: Date.now(),
      };
    }
    return next;
  } catch {
    return INITIAL_STATE;
  }
}

export interface DocumentProcessingContextValue {
  processingIds: Set<string>;
  isProcessing: (docId: string) => boolean;
  isBulkProcessing: boolean;
  bulkProgress: BulkProgress | null;
  lastUpdatedAt: number;
  hasAnyActivity: boolean;
  processOne: (
    docId: string,
    taxProfileId?: string,
  ) => Promise<ProcessDocumentResult | null>;
  processMany: (docIds: string[], taxProfileId?: string) => Promise<void>;
  reset: () => void;
}

export function DocumentProcessingProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PersistedState>(() => hydrateFromStorage());
  const runIdRef = useRef(0);

  // Persist state — skip the no-op initial write.
  useEffect(() => {
    if (
      state.processingIds.length === 0 &&
      !state.isBulkProcessing &&
      state.bulkProgress === null &&
      state.lastUpdatedAt === 0
    ) {
      try {
        localStorage.removeItem(STORAGE_KEY);
      } catch {
        /* ignore */
      }
      return;
    }
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* quota / private mode — ignore */
    }
  }, [state]);

  const processingIdSet = useMemo(
    () => new Set(state.processingIds),
    [state.processingIds],
  );

  const isProcessing = useCallback(
    (docId: string) => processingIdSet.has(docId),
    [processingIdSet],
  );

  const processOne = useCallback(
    async (
      docId: string,
      taxProfileId?: string,
    ): Promise<ProcessDocumentResult | null> => {
      const myRunId = runIdRef.current;
      setState((prev) => {
        if (prev.processingIds.includes(docId)) return prev;
        return { ...prev, processingIds: [...prev.processingIds, docId] };
      });
      try {
        const result = await processDocument(docId, taxProfileId);
        if (runIdRef.current !== myRunId) return null;
        return result;
      } catch (err) {
        console.error("processOne failed", err);
        return null;
      } finally {
        setState((prev) => ({
          ...prev,
          processingIds: prev.processingIds.filter((id) => id !== docId),
          lastUpdatedAt: Date.now(),
        }));
      }
    },
    [],
  );

  const processMany = useCallback(
    async (docIds: string[], taxProfileId?: string): Promise<void> => {
      if (docIds.length === 0) return;
      const myRunId = ++runIdRef.current;
      setState((prev) => ({
        ...prev,
        isBulkProcessing: true,
        bulkProgress: { total: docIds.length, completed: 0, errorCount: 0 },
      }));
      for (const docId of docIds) {
        if (runIdRef.current !== myRunId) break;
        setState((prev) => {
          if (prev.processingIds.includes(docId)) return prev;
          return { ...prev, processingIds: [...prev.processingIds, docId] };
        });
        let succeeded = false;
        try {
          await processDocument(docId, taxProfileId);
          succeeded = true;
        } catch (err) {
          console.error("processMany item failed", docId, err);
        } finally {
          setState((prev) => {
            const bulk = prev.bulkProgress
              ? {
                  total: prev.bulkProgress.total,
                  completed: prev.bulkProgress.completed + 1,
                  errorCount: prev.bulkProgress.errorCount + (succeeded ? 0 : 1),
                }
              : null;
            return {
              ...prev,
              processingIds: prev.processingIds.filter((id) => id !== docId),
              bulkProgress: bulk,
              lastUpdatedAt: Date.now(),
            };
          });
        }
      }
      setState((prev) => ({
        ...prev,
        isBulkProcessing: false,
        bulkProgress: null,
        lastUpdatedAt: Date.now(),
      }));
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

  const value: DocumentProcessingContextValue = {
    processingIds: processingIdSet,
    isProcessing,
    isBulkProcessing: state.isBulkProcessing,
    bulkProgress: state.bulkProgress,
    lastUpdatedAt: state.lastUpdatedAt,
    hasAnyActivity:
      state.isBulkProcessing || processingIdSet.size > 0,
    processOne,
    processMany,
    reset,
  };

  return (
    <DocumentProcessingContext.Provider value={value}>
      {children}
    </DocumentProcessingContext.Provider>
  );
}
