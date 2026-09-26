import { useEffect, useRef, useState, type CSSProperties } from "react";
import { motion } from "framer-motion";
import {
  createDeduction,
  getApiErrorMessage,
  getDocumentPreviewBlob,
  getExtractionDebug,
} from "../../services/api";
import type { DeductionCategory, ExtractionDebugResult, TaxProfile } from "../../types/api";
import { useLang, useTaxProfile } from "../../contexts/hooks";

type Props = {
  documentId: string;
  originalFilename: string;
  onClose: () => void;
};

function getExtension(filename: string): string {
  const idx = filename.lastIndexOf(".");
  if (idx === -1) return "";
  return filename.slice(idx + 1).toLowerCase();
}

function confidenceColor(confidence: number | undefined | null): string {
  if (confidence == null) return "var(--line-strong)";
  if (confidence >= 0.7) return "var(--positive)";
  if (confidence >= 0.5) return "var(--attention)";
  return "var(--danger)";
}

function formatField(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function localizedCategory(
  value: unknown,
  files: {
    catMedical: string;
    catEducation: string;
    catHousingInterest: string;
    catDonations: string;
    catInsurance: string;
    catPension: string;
  },
): string {
  const names: Record<string, string> = {
    medical: files.catMedical,
    education: files.catEducation,
    housing_interest: files.catHousingInterest,
    donations: files.catDonations,
    insurance: files.catInsurance,
    pension: files.catPension,
  };
  return names[String(value)] ?? formatField(value);
}

// A write rejected because the sent `If-Match` profile version is stale comes
// back as a conflict. Anything else (validation, network, server error) must
// not be treated as a version mismatch.
function isVersionConflict(error: unknown): boolean {
  if (typeof error !== "object" || error === null) return false;
  const response = (error as { response?: { status?: number } }).response;
  return response?.status === 409;
}

const eyebrow: CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: ".12em",
  textTransform: "uppercase",
  color: "var(--ink-faint)",
};

export default function DocumentPreviewModal({ documentId, originalFilename, onClose }: Props) {
  const { t } = useLang();
  const F = t.files;
  const { profile: taxProfile, refreshTaxProfile } = useTaxProfile();
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [blobError, setBlobError] = useState<string | null>(null);
  const [isBlobLoading, setIsBlobLoading] = useState(true);

  const [debug, setDebug] = useState<ExtractionDebugResult | null>(null);
  const [debugError, setDebugError] = useState<string | null>(null);
  const [isDebugLoading, setIsDebugLoading] = useState(true);

  const [showRawText, setShowRawText] = useState(false);
  const [copyStatus, setCopyStatus] = useState<"idle" | "copied">("idle");

  const reloadDebug = async () => {
    try {
      const result = await getExtractionDebug(documentId);
      setDebug(result);
    } catch (err) {
      console.error("Failed to reload extraction details", err);
    }
  };

  useEffect(() => {
    let revokedUrl: string | null = null;
    let cancelled = false;

    (async () => {
      try {
        setIsBlobLoading(true);
        setBlobError(null);
        const blob = await getDocumentPreviewBlob(documentId);
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        revokedUrl = url;
        setBlobUrl(url);
      } catch (err) {
        if (cancelled) return;
        setBlobError(getApiErrorMessage(err, F.previewLoadError));
      } finally {
        if (!cancelled) setIsBlobLoading(false);
      }
    })();

    (async () => {
      try {
        setIsDebugLoading(true);
        setDebugError(null);
        const result = await getExtractionDebug(documentId);
        if (cancelled) return;
        setDebug(result);
      } catch (err) {
        if (cancelled) return;
        setDebugError(getApiErrorMessage(err, F.extractionLoadError));
      } finally {
        if (!cancelled) setIsDebugLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      if (revokedUrl) URL.revokeObjectURL(revokedUrl);
    };
  }, [documentId, F.previewLoadError, F.extractionLoadError]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ext = getExtension(originalFilename);
  const isImage = ext === "jpg" || ext === "jpeg" || ext === "png";
  const isPdf = ext === "pdf";

  const handleCopyJson = async () => {
    if (!debug?.extracted_data) return;
    try {
      await navigator.clipboard.writeText(JSON.stringify(debug.extracted_data, null, 2));
      setCopyStatus("copied");
      setTimeout(() => setCopyStatus("idle"), 1500);
    } catch (err) {
      console.error("Clipboard write failed", err);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(20,15,5,0.55)", backdropFilter: "blur(4px)" }}
      onClick={onClose}
    >
      <motion.div
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        exit={{ scale: 0.95 }}
        onClick={(e) => e.stopPropagation()}
        className="card w-full max-w-7xl max-h-[90vh] flex flex-col overflow-hidden"
        style={{ boxShadow: "var(--shadow-lg)" }}
      >
        <div className="flex items-center justify-between px-6 py-4 shrink-0" style={{ borderBottom: "1px solid var(--line)" }}>
          <h3 className="t-h3 truncate pr-4" style={{ fontSize: 16 }} title={originalFilename}>
            {originalFilename}
          </h3>
          <button
            onClick={onClose}
            className="p-2 -mr-2 rounded-lg"
            style={{ color: "var(--ink-soft)", background: "transparent", border: "none" }}
            aria-label={F.previewClose}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 min-h-0 flex flex-col lg:flex-row">
          {/* Left: file preview */}
          <div className="flex-1 lg:basis-[55%] min-h-[40vh] flex items-center justify-center p-4 overflow-auto" style={{ background: "var(--paper-2)" }}>
            {isBlobLoading && (
              <div className="animate-spin" style={{ width: 32, height: 32, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)" }} />
            )}
            {!isBlobLoading && blobError && (
              <p className="px-6 text-center t-small" style={{ color: "var(--danger)" }}>
                {blobError}
              </p>
            )}
            {!isBlobLoading && !blobError && blobUrl && isImage && (
              <img src={blobUrl} alt={originalFilename} className="max-h-[75vh] max-w-full object-contain" />
            )}
            {!isBlobLoading && !blobError && blobUrl && isPdf && (
              <iframe src={blobUrl} title={originalFilename} className="w-full h-[75vh] rounded" style={{ background: "#fff" }} />
            )}
            {!isBlobLoading && !blobError && blobUrl && !isImage && !isPdf && (
              <div className="text-center px-6">
                <p className="t-small" style={{ marginBottom: 12 }}>
                  {F.previewUnavailable}
                </p>
                <a href={blobUrl} download={originalFilename} className="btn btn-primary btn-sm">
                  {F.previewDownload}
                </a>
              </div>
            )}
          </div>

          {/* Right: extraction panel */}
          <div
            className="lg:basis-[45%] lg:max-w-[45%] overflow-y-auto"
            style={{ borderInlineStart: "1px solid var(--line)", background: "var(--paper)" }}
          >
            <ExtractionPanel
              key={documentId}
              documentId={documentId}
              loading={isDebugLoading}
              error={debugError}
              debug={debug}
              taxProfile={taxProfile}
              onRefreshProfile={refreshTaxProfile}
              onReloadDebug={reloadDebug}
              showRawText={showRawText}
              onToggleRawText={() => setShowRawText((v) => !v)}
              copyStatus={copyStatus}
              onCopyJson={handleCopyJson}
            />
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}

type PanelProps = {
  documentId: string;
  loading: boolean;
  error: string | null;
  debug: ExtractionDebugResult | null;
  taxProfile: TaxProfile | null;
  onRefreshProfile: () => Promise<unknown>;
  onReloadDebug: () => Promise<void>;
  showRawText: boolean;
  onToggleRawText: () => void;
  copyStatus: "idle" | "copied";
  onCopyJson: () => void;
};

function ExtractionPanel({
  documentId,
  loading,
  error,
  debug,
  taxProfile,
  onRefreshProfile,
  onReloadDebug,
  showRawText,
  onToggleRawText,
  copyStatus,
  onCopyJson,
}: PanelProps) {
  const { t, fill } = useLang();
  const F = t.files;

  const [showManualForm, setShowManualForm] = useState(false);
  const [category, setCategory] = useState<DeductionCategory>("medical");
  const [amount, setAmount] = useState<string>("");
  const [date, setDate] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const submitInFlightRef = useRef(false);
  // Latched once the POST succeeds: the deduction exists, so no second POST may
  // be sent for this document even if the follow-up refresh/reload fails and
  // leaves the manual card on screen.
  const deductionCreatedRef = useRef(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  const [manualFormInitialized, setManualFormInitialized] = useState(false);
  const toggleManualForm = () => {
    if (!showManualForm && !manualFormInitialized && debug?.extracted_data) {
      const d = debug.extracted_data;
      if (d.amount != null) setAmount(String(d.amount));
      if (d.date) setDate(String(d.date));
      if (d.vendor) setDescription(String(d.vendor));
      if (
        d.category &&
        ["medical", "education", "housing_interest", "donations", "insurance", "pension"].includes(String(d.category))
      ) {
        setCategory(d.category as DeductionCategory);
      }
      setManualFormInitialized(true);
    }
    setShowManualForm((previous) => !previous);
  };

  if (loading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[40vh]">
        <div className="animate-spin" style={{ width: 26, height: 26, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)" }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <h4 style={{ ...eyebrow, marginBottom: 12 }}>{F.reviewTitle}</h4>
        <p className="t-small" style={{ color: "var(--danger)" }}>
          {error}
        </p>
      </div>
    );
  }

  if (!debug) return null;

  const status = debug.processing_status;
  const data = debug.extracted_data;
  const confidence = typeof data?.confidence === "number" ? data.confidence : null;
  const extractorBackend = data?.extractor_backend ?? "unknown";
  const relabeledFrom = data?.user_type_corrected_from as string | undefined;

  let routingHint = F.routingHintHigh;
  if (status === "failed") {
    routingHint = F.routingHintFailed;
  } else if (status === "pending") {
    routingHint = F.routingHintPending;
  } else if (data?.needs_review || (confidence != null && confidence < 0.85)) {
    routingHint = F.routingHintReview;
  }

  const docDateStr = (data?.date as string) || date || "";
  const docYear = docDateStr ? new Date(docDateStr).getFullYear() : null;
  const isYearMismatch = Boolean(
    docYear && !isNaN(docYear) && taxProfile?.tax_year && docYear !== taxProfile.tax_year
  );

  const handleConfirmDeduction = async (e: React.FormEvent) => {
    e.preventDefault();
    // A rapid double confirmation can deliver a second submit before React has
    // re-rendered the button as disabled, which would create a duplicate
    // deduction for the same document. Guard the handler itself, not only the
    // button's disabled state. `deductionCreatedRef` stays latched after a
    // successful write so no second POST can follow it.
    if (submitInFlightRef.current || deductionCreatedRef.current) return;
    if (!taxProfile) {
      setSubmitError(F.noActiveProfileError);
      return;
    }
    const parsedAmount = Number(amount);
    if (isNaN(parsedAmount) || parsedAmount <= 0) {
      setSubmitError(F.amountPositiveError);
      return;
    }
    submitInFlightRef.current = true;
    setIsSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);

    try {
      await createDeduction(
        {
          tax_profile_id: taxProfile.id,
          category,
          amount: parsedAmount,
          date: date || null,
          description: description.trim() || null,
          document_id: documentId,
        },
        taxProfile.version
      );
    } catch (err) {
      // The write itself failed, so the form stays retryable.
      setSubmitError(getApiErrorMessage(err, F.deductionSaveError));
      if (isVersionConflict(err)) {
        // Our `If-Match` version was stale: resync the profile so the retry
        // sends the refreshed version instead of replaying the rejected one.
        try {
          await onRefreshProfile();
        } catch (refreshErr) {
          console.error("Failed to resync tax profile version", refreshErr);
        }
      }
      submitInFlightRef.current = false;
      setIsSubmitting(false);
      return;
    }

    // The deduction now exists. Latch the guard so this document cannot be
    // posted twice, and report the save as successful even if the follow-up
    // refresh/reload below fails — a fresh read is not part of the write.
    deductionCreatedRef.current = true;
    setIsSubmitting(false);
    setSubmitSuccess(F.deductionAddedSuccess);

    try {
      await onRefreshProfile();
    } catch (refreshErr) {
      console.error("Deduction saved but profile refresh failed", refreshErr);
    }
    try {
      await onReloadDebug();
    } catch (reloadErr) {
      console.error("Deduction saved but extraction reload failed", reloadErr);
    }
  };

  if (status === "pending") {
    return (
      <div className="p-6 flex flex-col gap-5">
        <div>
          <h4 style={{ ...eyebrow, marginBottom: 8 }}>{F.reviewTitle}</h4>
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip chip-gold" style={{ textTransform: "uppercase" }}>
              {status}
            </span>
            <span className="t-small faint" style={{ fontStyle: "italic" }}>
              {routingHint}
            </span>
          </div>
        </div>

        <div className="p-4 rounded-xl text-center" style={{ background: "var(--paper-2)", border: "1px solid var(--line)" }}>
          <p className="t-body font-semibold" style={{ marginBottom: 4 }}>{F.statusPending}</p>
          <p className="t-small faint">{F.routingHintPending}</p>
        </div>

        {/* Manual entry fallback without AI */}
        {!debug.deduction && (
          <ManualReviewCard
            taxProfile={taxProfile}
            showManualForm={showManualForm}
            onToggleManualForm={toggleManualForm}
            category={category}
            setCategory={setCategory}
            amount={amount}
            setAmount={setAmount}
            date={date}
            setDate={setDate}
            description={description}
            setDescription={setDescription}
            isSubmitting={isSubmitting}
            submitError={submitError}
            submitSuccess={submitSuccess}
            onSubmit={handleConfirmDeduction}
          />
        )}
      </div>
    );
  }

  return (
    <div className="p-6 flex flex-col gap-5">
      <div>
        <h4 style={{ ...eyebrow, marginBottom: 8 }}>{F.reviewTitle}</h4>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`chip ${status === "processed" ? "chip-green" : "chip-clay"}`} style={{ textTransform: "uppercase" }}>
            {status === "processed" ? F.statusProcessed : F.statusFailed}
          </span>
          <span className="chip" style={{ fontFamily: "var(--font-mono)", maxWidth: "24ch", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={extractorBackend}>
            {extractorBackend}
          </span>
          {confidence != null && (
            <div className="flex items-center gap-2 ml-auto">
              <span className="t-small faint">{F.confidenceLabel}</span>
              <div style={{ width: 80, height: 6, borderRadius: 999, background: "var(--line)", overflow: "hidden" }}>
                <div style={{ height: "100%", background: confidenceColor(confidence), width: `${Math.round(confidence * 100)}%` }} />
              </div>
              <span className="num t-small" style={{ width: 32, textAlign: "right", color: "var(--ink-soft)" }}>
                {Math.round(confidence * 100)}%
              </span>
            </div>
          )}
        </div>
        <div className="t-small" style={{ marginTop: 6, color: "var(--ink-soft)", fontStyle: "italic" }}>
          {routingHint}
        </div>
      </div>

      {isYearMismatch && (
        <div
          data-testid="year-mismatch-warning"
          style={{
            padding: "10px 14px",
            borderRadius: 10,
            background: "var(--clay-tint, rgba(199,85,55,0.08))",
            color: "var(--danger, #c75537)",
            border: "1px solid var(--clay-line, rgba(199,85,55,0.25))",
            fontSize: 12.5,
            lineHeight: 1.4,
          }}
        >
          <strong>⚠️ {fill(F.yearMismatchWarning, { docYear: String(docYear), profileYear: String(taxProfile?.tax_year) })}</strong>
        </div>
      )}

      {status === "failed" && data?.error && (
        <div className="t-small" style={{ padding: "8px 12px", borderRadius: 10, background: "var(--clay-tint)", color: "var(--danger)" }}>
          <span style={{ ...eyebrow, color: "var(--danger)", display: "block", marginBottom: 4 }}>{F.extractionErrorLabel}</span>
          <span style={{ wordBreak: "break-word" }}>{String(data.error)}</span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Field label={F.vendorLabel} value={formatField(data?.vendor)} />
        <Field
          label={F.amountLabel}
          value={data?.amount != null ? Number(data.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
        />
        <Field label={F.dateLabel} value={formatField(data?.date)} />
        <Field label={F.categoryLabel} value={localizedCategory(data?.category, F)} />
        <Field label={F.documentTypeLabel} value={formatField(data?.document_type)} hint={relabeledFrom ? fill(F.relabeledFrom, { type: relabeledFrom }) : undefined} />
      </div>

      <DeductionBadge debug={debug} />

      {/* Manual verification / entry card */}
      {!debug.deduction && (
        <ManualReviewCard
          taxProfile={taxProfile}
          showManualForm={showManualForm}
          onToggleManualForm={toggleManualForm}
          category={category}
          setCategory={setCategory}
          amount={amount}
          setAmount={setAmount}
          date={date}
          setDate={setDate}
          description={description}
          setDescription={setDescription}
          isSubmitting={isSubmitting}
          submitError={submitError}
          submitSuccess={submitSuccess}
          onSubmit={handleConfirmDeduction}
        />
      )}

      {data?.raw_text && (
        <div>
          <button
            onClick={onToggleRawText}
            className="t-small"
            style={{ color: "var(--ink-soft)", background: "transparent", border: "none", display: "flex", alignItems: "center", gap: 4 }}
          >
            <svg className="w-3 h-3" style={{ transform: showRawText ? "rotate(90deg)" : "none", transition: "transform .15s" }} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
            </svg>
            {showRawText ? F.hideRawText : F.showRawText}
          </button>
          {showRawText && (
            <pre
              className="num"
              style={{ marginTop: 8, maxHeight: 256, overflow: "auto", padding: 12, borderRadius: 10, background: "var(--paper-2)", border: "1px solid var(--line)", fontSize: 11, color: "var(--ink-soft)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}
            >
              {data.raw_text}
            </pre>
          )}
        </div>
      )}

      {data && (
        <button onClick={onCopyJson} className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }}>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m-6-8h6M5 4h14a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V5a1 1 0 011-1z" />
          </svg>
          {copyStatus === "copied" ? F.copied : F.copyRawJson}
        </button>
      )}
    </div>
  );
}

function Field({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div style={{ ...eyebrow, fontSize: 10, marginBottom: 4 }}>{label}</div>
      <div style={{ color: "var(--ink)", wordBreak: "break-word" }}>{value}</div>
      {hint && <div className="t-small" style={{ color: "var(--attention)", fontStyle: "italic", marginTop: 2, fontSize: 10 }}>{hint}</div>}
    </div>
  );
}

function DeductionBadge({ debug }: { debug: ExtractionDebugResult }) {
  const { t, fill } = useLang();
  const F = t.files;
  if (debug.deduction) {
    const d = debug.deduction;
    const amount = d.amount != null ? Number(d.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
    return (
      <div className="t-small" style={{ padding: "10px 12px", borderRadius: 10, background: "var(--green-tint)", color: "var(--green)" }}>
        <span style={{ ...eyebrow, color: "var(--green)", display: "block", marginBottom: 4 }}>✓ {F.deductionCreatedLabel}</span>
        <span style={{ color: "var(--ink)" }}>
          {localizedCategory(d.category, F)} — {amount} {F.currencyUnit}{d.date ? ` ${fill(F.onDate, { date: d.date })}` : ""}
        </span>
      </div>
    );
  }

  if (debug.processing_status === "processed") {
    return (
      <div className="t-small" style={{ padding: "10px 12px", borderRadius: 10, background: "var(--paper-2)", border: "1px solid var(--line)", color: "var(--ink-soft)" }}>
        <span style={{ ...eyebrow, display: "block", marginBottom: 4 }}>{F.deductionNotCreatedLabel}</span>
        <span className="faint">{F.deductionNotCreatedHelp}</span>
      </div>
    );
  }

  return null;
}

type ManualReviewCardProps = {
  taxProfile: TaxProfile | null;
  showManualForm: boolean;
  onToggleManualForm: () => void;
  category: DeductionCategory;
  setCategory: (c: DeductionCategory) => void;
  amount: string;
  setAmount: (a: string) => void;
  date: string;
  setDate: (d: string) => void;
  description: string;
  setDescription: (d: string) => void;
  isSubmitting: boolean;
  submitError: string | null;
  submitSuccess: string | null;
  onSubmit: (e: React.FormEvent) => void;
};

function ManualReviewCard({
  taxProfile,
  showManualForm,
  onToggleManualForm,
  category,
  setCategory,
  amount,
  setAmount,
  date,
  setDate,
  description,
  setDescription,
  isSubmitting,
  submitError,
  submitSuccess,
  onSubmit,
}: ManualReviewCardProps) {
  const { t } = useLang();
  const F = t.files;

  return (
    <div
      data-testid="manual-review-card"
      style={{
        padding: 16,
        borderRadius: 12,
        background: "var(--paper-2)",
        border: "1px solid var(--line)",
        display: "flex",
        flexDirection: "column",
        gap: 12,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
        <div>
          <h5 style={{ ...eyebrow, fontSize: 11, color: "var(--ink)" }}>{F.manualEntryTitle}</h5>
          <p className="t-small faint" style={{ fontSize: 11.5, marginTop: 2 }}>{F.manualEntrySub}</p>
        </div>
        <button
          type="button"
          onClick={onToggleManualForm}
          className="btn btn-ghost btn-sm"
          style={{ fontSize: 12, flex: "none" }}
        >
          {showManualForm ? t.common.cancel : F.manualEntryBtn}
        </button>
      </div>

      {showManualForm && (
        <form
          onSubmit={onSubmit}
          style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}
        >
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={{ ...eyebrow, fontSize: 10, display: "block", marginBottom: 4 }}>
                {F.categoryLabel}
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as DeductionCategory)}
                className="input input-sm w-full"
                style={{ fontSize: 12.5 }}
              >
                <option value="medical">{F.catMedical}</option>
                <option value="education">{F.catEducation}</option>
                <option value="housing_interest">{F.catHousingInterest}</option>
                <option value="donations">{F.catDonations}</option>
                <option value="insurance">{F.catInsurance}</option>
                <option value="pension">{F.catPension}</option>
              </select>
            </div>
            <div>
              <label style={{ ...eyebrow, fontSize: 10, display: "block", marginBottom: 4 }}>
                {F.amountLabel}
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
                className="input input-sm w-full"
                style={{ fontSize: 12.5 }}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label style={{ ...eyebrow, fontSize: 10, display: "block", marginBottom: 4 }}>
                {F.dateLabel}
              </label>
              <input
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="input input-sm w-full"
                style={{ fontSize: 12.5 }}
              />
            </div>
            <div>
              <label style={{ ...eyebrow, fontSize: 10, display: "block", marginBottom: 4 }}>
                {F.descriptionLabel}
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={F.vendorPlaceholder}
                className="input input-sm w-full"
                style={{ fontSize: 12.5 }}
              />
            </div>
          </div>

          {submitError && (
            <p className="t-small" style={{ color: "var(--danger)", fontSize: 12 }}>
              {submitError}
            </p>
          )}

          {submitSuccess && (
            <p className="t-small" style={{ color: "var(--positive)", fontSize: 12, fontWeight: 600 }}>
              {submitSuccess}
            </p>
          )}

          <button
            type="submit"
            disabled={isSubmitting || Boolean(submitSuccess) || !taxProfile || !amount || Number(amount) <= 0}
            className="btn btn-primary btn-sm"
            style={{ alignSelf: "flex-end", marginTop: 4 }}
          >
            {isSubmitting ? t.common.loading : F.confirmAndAddBtn}
          </button>
        </form>
      )}
    </div>
  );
}
