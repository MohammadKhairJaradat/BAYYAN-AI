import { useState, useEffect, useRef, type CSSProperties } from "react";
import { api, getApiErrorMessage, usageRequestHeaders } from "../services/api";
import { useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import DocumentPreviewModal from "../components/ui/document-preview-modal";
import { useTaxProfile } from "../contexts/hooks";
import { useDocumentProcessing } from "../contexts/hooks";
import { useLang } from "../contexts/hooks";
import { Icon, Button } from "../components/brand";
import {
  DocumentRequirementsCard,
  DocumentStatusExplainer,
  QuotaUsageIndicator,
} from "../components/guidance";

export type ReviewStatus = "confirmed" | "processing" | "pending" | "failed" | "needs_review" | "awaiting_confirmation";

export type Document = {
  id: string;
  original_filename: string;
  document_type: string;
  upload_date: string;
  processing_status: string;
  extracted_data?: { error?: string; needs_review?: boolean; awaiting_confirmation?: boolean; status?: string; [k: string]: unknown } | null;
  has_linked_deduction?: boolean;
};

// eslint-disable-next-line react-refresh/only-export-components
export function getDocumentReviewStatus(
  doc: {
    processing_status: string;
    extracted_data?: { error?: string; needs_review?: boolean; awaiting_confirmation?: boolean; status?: string; [k: string]: unknown } | null;
    has_linked_deduction?: boolean;
  },
  isProcessing: boolean = false,
): ReviewStatus {
  if (doc.has_linked_deduction) return "confirmed";
  if (isProcessing) return "processing";
  if (doc.processing_status === "pending") return "pending";
  if (doc.processing_status === "failed") return "failed";
  if (doc.processing_status === "processed") {
    if (doc.extracted_data?.needs_review === true) return "needs_review";
    if (doc.extracted_data?.awaiting_confirmation === true || doc.extracted_data?.status === "awaiting_confirmation") {
      return "awaiting_confirmation";
    }
    if (doc.extracted_data && !doc.extracted_data.error) {
      return "awaiting_confirmation";
    }
    return "needs_review";
  }
  return "pending";
}

const titleCase = (s: string) => s.replace("_", " ").replace(/\b\w/g, (l) => l.toUpperCase());

export default function Files() {
  const { t } = useLang();
  const F = t.files;
  const [searchParams, setSearchParams] = useSearchParams();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showGuide, setShowGuide] = useState(false);

  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingUploadFile, setPendingUploadFile] = useState<File | null>(null);
  const [selectedDocType, setSelectedDocType] = useState<string>("receipt");
  const [previewDoc, setPreviewDoc] = useState<Document | null>(null);

  const { profile: taxProfile, refreshTaxProfile } = useTaxProfile();
  const taxProfileId = taxProfile?.id;
  const { processingIds, isBulkProcessing, processOne, processMany, lastUpdatedAt } = useDocumentProcessing();

  const fetchDocuments = async () => {
    try {
      setIsLoading(true);
      const params: Record<string, string> = {};
      searchParams.forEach((value, key) => {
        if (key !== "review_status") {
          params[key] = value;
        }
      });
      const res = await api.get("/documents", { params });
      const sortedDocs = (res.data as Document[]).sort(
        (a, b) => new Date(b.upload_date).getTime() - new Date(a.upload_date).getTime(),
      );
      setDocuments(sortedDocs);
    } catch (error) {
      console.error("Failed to fetch documents", error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    if (lastUpdatedAt === 0) return;
    fetchDocuments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastUpdatedAt]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setPendingUploadFile(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const executeUpload = async () => {
    if (!pendingUploadFile) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", pendingUploadFile);
    formData.append("document_type", selectedDocType);
    try {
      await api.post("/documents/upload", formData, { headers: { "Content-Type": "multipart/form-data", ...usageRequestHeaders() } });
      setPendingUploadFile(null);
      fetchDocuments();
    } catch (error) {
      console.error("Upload failed", error);
      alert(getApiErrorMessage(error, t.common.error));
    } finally {
      setIsUploading(false);
    }
  };

  const handleProcessFile = async (documentId: string) => {
    const result = await processOne(documentId, taxProfileId);
    if (!result) return;
    setDocuments((prev) =>
      prev.map((d) =>
        d.id === documentId
          ? { ...d, processing_status: result.processing_status, extracted_data: result.extracted_data as Document["extracted_data"] }
          : d,
      ),
    );
    if (result.deduction_id) {
      refreshTaxProfile().catch((err) => console.error("Failed to refresh tax profile after extraction", err));
    }
  };

  const handleProcessAllPending = async () => {
    const pendingIds = documents.filter((d) => d.processing_status === "pending").map((d) => d.id);
    if (pendingIds.length === 0) return;
    const hadTaxProfile = !!taxProfileId;
    await processMany(pendingIds, taxProfileId);
    if (hadTaxProfile) {
      refreshTaxProfile().catch((err) => console.error("Failed to refresh tax profile after bulk extraction", err));
    }
  };

  const docTypeLabels: Record<string, string> = {
    receipt: F.docTypeReceipt,
    salary_slip: F.docTypeSalarySlip,
    bank_statement: F.docTypeBankStatement,
  };

  const statusLabels: Record<string, string> = {
    pending: F.statusPending,
    processed: F.statusProcessed,
    failed: F.statusFailed,
  };

  const handleDeleteFile = async (documentId: string) => {
    if (!window.confirm(F.deleteConfirm)) return;
    try {
      await api.delete(`/documents/${documentId}`);
      setDocuments((prev) => prev.filter((doc) => doc.id !== documentId));
    } catch (error) {
      console.error("Failed to delete document", error);
      alert(t.common.error);
    }
  };

  const isActiveFilter = (key: string, value: string | null) =>
    value === null ? !searchParams.has(key) : searchParams.get(key) === value;

  const setFilter = (key: string, value: string | null) => {
    if (value === null) searchParams.delete(key);
    else searchParams.set(key, value);
    setSearchParams(searchParams);
  };

  const sideBtn = (active: boolean): CSSProperties => ({
    width: "100%",
    textAlign: "start",
    padding: "7px 12px",
    borderRadius: 9,
    fontSize: 13.5,
    fontWeight: 500,
    border: "none",
    background: active ? "var(--green-tint)" : "transparent",
    color: active ? "var(--green)" : "var(--ink-soft)",
  });

  const statusChip = (status: string) => {
    if (status === "pending") return "chip chip-gold";
    if (status === "processed") return "chip chip-green";
    if (status === "failed") return "chip chip-clay";
    return "chip";
  };

  const isAr = t.dir === "rtl";

  const reviewStatusChip = (status: ReviewStatus) => {
    if (status === "confirmed") return "chip chip-green";
    if (status === "processing") return "chip chip-gold";
    if (status === "pending") return "chip chip-gold";
    if (status === "awaiting_confirmation") return "chip chip-green";
    if (status === "needs_review") return "chip chip-clay";
    if (status === "failed") return "chip chip-clay";
    return "chip";
  };

  const getReviewStatusLabel = (status: ReviewStatus) => {
    switch (status) {
      case "confirmed":
        return isAr ? "مؤكد" : "Confirmed";
      case "processing":
        return F.reviewStatusProcessing;
      case "pending":
        return F.reviewStatusPending;
      case "awaiting_confirmation":
        return F.reviewStatusAwaitingConfirmation;
      case "needs_review":
        return F.reviewStatusNeedsReview;
      case "failed":
        return F.reviewStatusFailed;
    }
  };

  const selectedReviewStatus = searchParams.get("review_status");

  const displayedDocuments = documents.filter((doc) => {
    if (!selectedReviewStatus) return true;
    const status = getDocumentReviewStatus(doc, processingIds.has(doc.id));
    return status === selectedReviewStatus;
  });

  const pendingCount = documents.filter((d) => d.processing_status === "pending").length;

  const th: CSSProperties = {
    textAlign: "start",
    padding: "12px 16px",
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: ".06em",
    textTransform: "uppercase",
    color: "var(--ink-faint)",
    borderBottom: "1px solid var(--line)",
  };
  const td: CSSProperties = { padding: "12px 16px", borderBottom: "1px solid var(--line)" };

  return (
    <div className="wrap wrap-app" style={{ paddingBlock: "40px 64px", display: "flex", gap: 28 }}>
      {/* Preview Modal */}
      <AnimatePresence>
        {previewDoc && (
          <DocumentPreviewModal
            documentId={previewDoc.id}
            originalFilename={previewDoc.original_filename}
            onClose={() => setPreviewDoc(null)}
          />
        )}
      </AnimatePresence>

      {/* Upload Modal */}
      <AnimatePresence>
        {pendingUploadFile && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: "rgba(20,15,5,0.55)", backdropFilter: "blur(4px)" }}
          >
            <motion.div
              initial={{ scale: 0.96 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.96 }}
              className="card card-pad"
              style={{ width: "100%", maxWidth: 420, boxShadow: "var(--shadow-lg)" }}
            >
              <h3 className="t-h3" style={{ marginBottom: 6 }}>
                {F.docTypeModalTitle}
              </h3>
              <p className="t-small" style={{ marginBottom: 20 }}>
                {pendingUploadFile.name}
              </p>
              <div className="stack" style={{ ["--gap"]: "10px", marginBottom: 20 } as CSSProperties}>
                {[
                  { type: "receipt", hint: F.typeHintReceipt },
                  { type: "salary_slip", hint: F.typeHintSalary },
                  { type: "bank_statement", hint: F.typeHintBank },
                ].map(({ type, hint }) => {
                  const active = selectedDocType === type;
                  return (
                    <label
                      key={type}
                      className="row"
                      style={{
                        padding: 12,
                        borderRadius: 12,
                        cursor: "pointer",
                        border: "1px solid " + (active ? "var(--green)" : "var(--line)"),
                        background: active ? "var(--green-tint)" : "var(--paper)",
                        color: active ? "var(--green)" : "var(--ink)",
                        alignItems: "flex-start",
                        gap: 12,
                      }}
                    >
                      <input
                        type="radio"
                        name="docType"
                        value={type}
                        checked={active}
                        onChange={() => setSelectedDocType(type)}
                        style={{ accentColor: "var(--green)", marginTop: 4 }}
                      />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>
                          {docTypeLabels[type] ?? titleCase(type)}
                        </div>
                        <div className="t-small" style={{ color: "var(--ink-soft)", marginTop: 2, fontSize: 12 }}>
                          {hint}
                        </div>
                      </div>
                    </label>
                  );
                })}
              </div>
              <div className="row" style={{ justifyContent: "flex-end", gap: 10 }}>
                <Button variant="quiet" onClick={() => setPendingUploadFile(null)}>
                  {t.common.cancel}
                </Button>
                <Button variant="primary" onClick={executeUpload} disabled={isUploading} icon={isUploading ? "refresh" : "upload"}>
                  {isUploading ? t.common.loading : F.upload}
                </Button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <aside className="max-md:hidden" style={{ width: 210, flex: "none", display: "flex", flexDirection: "column", gap: 24, position: "sticky", top: 88, alignSelf: "flex-start" }}>
        <button onClick={() => setSearchParams({})} className="row" style={sideBtn(Array.from(searchParams.keys()).length === 0)}>
          <Icon name="folder" size={17} />
          {F.filters[0]}
        </button>
        <FilterGroup title={F.filterByType}>
          {["receipt", "salary_slip", "bank_statement"].map((type) => (
            <button key={type} onClick={() => setFilter("document_type", type)} style={sideBtn(isActiveFilter("document_type", type))}>
              {docTypeLabels[type] ?? titleCase(type)}
            </button>
          ))}
        </FilterGroup>
        <FilterGroup title={F.filterByStatus}>
          {["pending", "processed", "failed"].map((status) => (
            <button key={status} onClick={() => setFilter("processing_status", status)} style={{ ...sideBtn(isActiveFilter("processing_status", status)), textTransform: "capitalize" }}>
              {statusLabels[status] ?? status}
            </button>
          ))}
        </FilterGroup>
        <FilterGroup title={F.filterByReviewStatus}>
          {[
            { key: "confirmed", label: isAr ? "مؤكد" : "Confirmed" },
            { key: "awaiting_confirmation", label: F.reviewStatusAwaitingConfirmation },
            { key: "needs_review", label: F.reviewStatusNeedsReview },
            { key: "pending", label: F.reviewStatusPending },
            { key: "failed", label: F.reviewStatusFailed },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setFilter("review_status", key)}
              style={sideBtn(isActiveFilter("review_status", key))}
            >
              {label}
            </button>
          ))}
        </FilterGroup>
        <FilterGroup title={F.filterByCategory}>
          {["medical", "education", "housing_interest", "donations", "insurance", "pension"].map((cat) => (
            <button key={cat} onClick={() => setFilter("category", cat)} style={sideBtn(isActiveFilter("category", cat))}>
              {titleCase(cat)}
            </button>
          ))}
        </FilterGroup>
      </aside>

      {/* Main */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="row-between" style={{ marginBottom: 20, gap: 16, flexWrap: "wrap" }}>
          <div>
            <h1 className="display t-h1" style={{ marginBottom: 6 }}>
              {F.title}
            </h1>
            <p className="t-body">{F.sub}</p>
          </div>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <Button
              variant="quiet"
              onClick={() => setShowGuide(!showGuide)}
              icon={showGuide ? "x" : "doc"}
            >
              {showGuide ? F.guidanceToggleHide : F.guidanceToggleShow}
            </Button>
            {pendingCount > 0 && (
              <Button variant="clay" onClick={handleProcessAllPending} disabled={isBulkProcessing} icon={isBulkProcessing ? "refresh" : "bolt"}>
                {isBulkProcessing ? t.common.loading : `${F.processing} ${pendingCount}`}
              </Button>
            )}
            <input type="file" ref={fileInputRef} className="hidden" onChange={handleFileSelect} accept=".jpg,.jpeg,.png,.pdf" />
            <Button variant="primary" onClick={() => fileInputRef.current?.click()} icon="upload">
              {F.upload}
            </Button>
          </div>
        </div>

        {/* Quota Usage Meter */}
        <div style={{ marginBottom: 20 }}>
          <QuotaUsageIndicator compact={true} showExemptions={false} />
        </div>

        {/* Expandable Guidance Cards */}
        {showGuide && (
          <div style={{ marginBottom: 24 }}>
            <DocumentRequirementsCard defaultExpanded={true} />
            <DocumentStatusExplainer defaultExpanded={true} />
          </div>
        )}

        <div className="card" style={{ overflow: "hidden" }}>
          {isLoading ? (
            <div style={{ display: "grid", placeItems: "center", padding: 80 }}>
              <div style={{ width: 30, height: 30, borderRadius: 999, border: "3px solid var(--green-tint2)", borderTopColor: "var(--green)", animation: "spin 1s linear infinite" }} />
              <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
            </div>
          ) : documents.length === 0 ? (
            <div className="center" style={{ padding: 64 }}>
              <Icon name="folder" size={42} color="var(--ink-faint)" style={{ margin: "0 auto 14px" }} />
              <p className="t-small">{F.empty}</p>
              {!showGuide && (
                <div style={{ marginTop: 16 }}>
                  <Button variant="quiet" onClick={() => setShowGuide(true)} icon="doc">
                    {F.guidanceToggleShow}
                  </Button>
                </div>
              )}
            </div>
          ) : displayedDocuments.length === 0 ? (
            <div className="center" style={{ padding: 64 }}>
              <Icon name="folder" size={42} color="var(--ink-faint)" style={{ margin: "0 auto 14px" }} />
              <p className="t-small">{F.noMatch}</p>
              <div style={{ marginTop: 16 }}>
                <Button variant="quiet" onClick={() => setSearchParams({})} icon="refresh">
                  {F.filters[0]}
                </Button>
              </div>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr>
                    <th style={th}>{F.filenameCol}</th>
                    <th style={th}>{F.uploadedCol}</th>
                    <th style={th}>{F.typeCol}</th>
                    <th style={th}>{F.statusCol}</th>
                    <th style={th}>{F.reviewStatusCol}</th>
                    <th style={{ ...th, textAlign: "end" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {displayedDocuments.map((doc) => {
                    const isProcessing = processingIds.has(doc.id);
                    const revStatus = getDocumentReviewStatus(doc, isProcessing);
                    return (
                      <tr key={doc.id}>
                        <td style={td}>
                          <div className="row" style={{ gap: 12 }}>
                            <div style={{ width: 32, height: 32, borderRadius: 8, background: "var(--green-tint)", display: "grid", placeItems: "center", flex: "none" }}>
                              <Icon name="doc" size={16} color="var(--green)" />
                            </div>
                            <div style={{ minWidth: 0 }}>
                              <span style={{ color: "var(--ink)", fontWeight: 600, display: "block", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", maxWidth: 280 }}>
                                {doc.original_filename}
                              </span>
                              {doc.processing_status === "failed" && (
                                <span className="t-small" style={{ color: "var(--danger)", fontStyle: "italic" }} title={doc.extracted_data?.error ? String(doc.extracted_data.error) : "Extraction failed"}>
                                  {F.extractionFailedRetry}
                                </span>
                              )}
                            </div>
                          </div>
                        </td>
                        <td style={{ ...td, color: "var(--ink-soft)", fontSize: 13 }}>
                          {new Date(doc.upload_date).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
                        </td>
                        <td style={{ ...td, color: "var(--ink-soft)", fontSize: 13 }}>
                          {docTypeLabels[doc.document_type] ?? titleCase(doc.document_type)}
                        </td>
                        <td style={td}>
                          <span
                            className={statusChip(doc.processing_status)}
                            title={
                              doc.processing_status === "pending"
                                ? F.statusTooltipPending
                                : doc.processing_status === "processed"
                                  ? F.statusTooltipProcessed
                                  : F.statusTooltipFailed
                            }
                          >
                            {statusLabels[doc.processing_status] ?? doc.processing_status}
                          </span>
                        </td>
                        <td style={td}>
                          <span
                            className={reviewStatusChip(revStatus)}
                            data-testid={`review-status-${doc.id}`}
                            title={getReviewStatusLabel(revStatus)}
                          >
                            {getReviewStatusLabel(revStatus)}
                          </span>
                        </td>
                        <td style={{ ...td, textAlign: "end" }}>
                          <div className="row" style={{ justifyContent: "flex-end", gap: 6 }}>
                            {(doc.processing_status === "pending" || doc.processing_status === "failed") && (
                              <button
                                type="button"
                                onClick={() => handleProcessFile(doc.id)}
                                disabled={isProcessing || isBulkProcessing}
                                className="btn btn-sm btn-clay"
                                style={{ padding: "6px 10px", fontSize: 12.5 }}
                                title={doc.processing_status === "failed" ? F.retryProcess : F.read}
                              >
                                <Icon name={isProcessing ? "refresh" : doc.processing_status === "failed" ? "refresh" : "bolt"} size={14} />
                                <span>{doc.processing_status === "failed" ? F.retryProcess : F.read}</span>
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => setPreviewDoc(doc)}
                              className="btn btn-sm btn-quiet"
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: 5,
                                padding: "6px 10px",
                                borderRadius: 8,
                                border: "1px solid var(--line)",
                                background: "transparent",
                                color: "var(--green)",
                                fontSize: 12.5,
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                              title={F.reviewDoc}
                              aria-label={`${F.reviewAction}: ${doc.original_filename}`}
                            >
                              <Icon name="eye" size={15} color="var(--green)" />
                              <span>{F.reviewAction}</span>
                            </button>
                            <IconBtn onClick={() => handleDeleteFile(doc.id)} disabled={isProcessing || isBulkProcessing} icon="trash" title={F.delete} color="var(--danger)" />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="t-eyebrow" style={{ color: "var(--ink-faint)", fontSize: 10.5, marginBottom: 8, paddingInline: 12 }}>
        {title}
      </h3>
      <div className="stack" style={{ ["--gap"]: "2px" } as CSSProperties}>
        {children}
      </div>
    </div>
  );
}

function IconBtn({
  onClick,
  icon,
  title,
  color,
  disabled,
}: {
  onClick: () => void;
  icon: Parameters<typeof Icon>[0]["name"];
  title: string;
  color: string;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      style={{ padding: 8, borderRadius: 9, border: "none", background: "transparent", color, opacity: disabled ? 0.45 : 1 }}
    >
      <Icon name={icon} size={18} color="currentColor" />
    </button>
  );
}
