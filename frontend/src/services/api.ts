import axios from "axios";
import type { AxiosError, AxiosRequestConfig } from "axios";
import type {
  AdminStats,
  AdminUserDetail,
  AdminUserList,
  AdminUserListQuery,
  AdminUserUpdate,
  AdvisorLatestReport,
  AdvisorLang,
  AdvisorReport,
  CalendarEvent,
  ChatMessage,
  ChatMessageCreatePayload,
  ChatProfileUpdateApply,
  ChatRequest,
  ChatResponse,
  ChatSession,
  ChatSessionWithMessages,
  Deduction,
  DeductionCreate,
  DeductionUpdate,
  ExtractionDebugResult,
  IncomeSource,
  IncomeSourceCreate,
  IncomeSourceUpdate,
  MaritalStatus,
  NotificationItem,
  PublicCapabilities,
  TaxCalculationResult,
  TaxProfile,
  TaxProfileUpdate,
  TaxWorkspacePreview,
  TaxWorkspaceRun,
  TokenResponse,
  User,
  UserUsage,
  UserUpdatePayload,
} from "../types/api";

const browserHost = typeof window !== "undefined" && window.location.hostname === "127.0.0.1"
  ? "127.0.0.1" : "localhost";
const configuredApiUrl = import.meta.env.VITE_API_URL || `http://${browserHost}:8000/api/v1`;
const apiUrl = new URL(configuredApiUrl);
if (["localhost", "127.0.0.1"].includes(apiUrl.hostname) &&
    typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)) {
  apiUrl.hostname = window.location.hostname;
}
const API_URL = apiUrl.toString().replace(/\/$/, "");

export function usageRequestHeaders(): Record<string, string> {
  return { "Idempotency-Key": crypto.randomUUID() };
}

export async function getPublicCapabilities(): Promise<PublicCapabilities> {
  const response = await axios.get<PublicCapabilities>(`${API_URL}/capabilities`, {
    timeout: 5000,
  });
  return response.data;
}

// Older releases persisted bearer tokens in localStorage. Drop them once on
// startup; only the HttpOnly refresh cookie survives a page reload now.
localStorage.removeItem("access_token");
localStorage.removeItem("refresh_token");
let accessToken: string | null = null;

export const tokenStore = {
  getAccess: () => accessToken,
  set: (tokens: TokenResponse) => {
    accessToken = tokens.access_token;
  },
  clear: () => {
    accessToken = null;
  },
};

export const api = axios.create({
  baseURL: API_URL,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use((config) => {
  const token = tokenStore.getAccess();
  if (token) {
    config.headers = config.headers ?? {};
    (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshing: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const priorToken = accessToken;
  try {
    const resp = await axios.post<TokenResponse>(
      `${API_URL}/auth/refresh`,
      {},
      { withCredentials: true }
    );
    tokenStore.set(resp.data);
    return resp.data.access_token;
  } catch {
    if (accessToken === priorToken) tokenStore.clear();
    return null;
  }
}

export function refreshAccessToken(): Promise<string | null> {
  if (!refreshing) {
    refreshing = performRefresh().finally(() => { refreshing = null; });
  }
  return refreshing;
}

api.interceptors.response.use(
  (resp) => resp,
  async (error: AxiosError) => {
    const original = error.config as
      | (AxiosRequestConfig & { _retry?: boolean })
      | undefined;

    const isAuthMutation = /^\/auth\/(login|signup|refresh|logout)$/.test(original?.url ?? "");
    if (error.response?.status === 401 && original && !original._retry && !isAuthMutation) {
      original._retry = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers = original.headers ?? {};
        (original.headers as Record<string, string>).Authorization = `Bearer ${newToken}`;
        return api(original);
      }
    }
    return Promise.reject(error);
  }
);

// ── Advisor / tax-profile helpers ────────────────────────────────────────────

function versionConfig(expectedVersion?: number): AxiosRequestConfig | undefined {
  return expectedVersion === undefined ? undefined : { headers: { "If-Match": String(expectedVersion) } };
}

export async function getOrCreateCurrentTaxProfile(
  userId: string,
  defaults: {
    marital_status: MaritalStatus;
    num_dependents: number;
  } & Partial<TaxProfileUpdate>,
  taxYear = new Date().getFullYear(),
): Promise<TaxProfile> {
  const list = await api.get<TaxProfile[]>("/tax-profiles/");
  const existing = list.data.find((p) => p.tax_year === taxYear);
  if (existing) return existing;

  const created = await api.post<TaxProfile>("/tax-profiles/", {
    user_id: userId,
    tax_year: taxYear,
    marital_status: defaults.marital_status,
    num_dependents: defaults.num_dependents,
    filing_status: defaults.filing_status ?? "individual",
    residency_status: defaults.residency_status ?? "resident",
    claims_dependents_exemption:
      defaults.claims_dependents_exemption ??
      (defaults.marital_status === "married" || defaults.num_dependents > 0),
    claim_spouse_expense_exemption:
      defaults.claim_spouse_expense_exemption ??
      (defaults.marital_status === "married"),
    disability_exemption_count: defaults.disability_exemption_count ?? 0,
  });
  return created.data;
}

export async function listTaxProfiles(): Promise<TaxProfile[]> {
  const resp = await api.get<TaxProfile[]>("/tax-profiles/");
  return resp.data;
}

export async function updateTaxProfile(
  id: string,
  payload: TaxProfileUpdate,
  expectedVersion?: number,
): Promise<TaxProfile> {
  const resp = await api.put<TaxProfile>(`/tax-profiles/${id}`, payload, versionConfig(expectedVersion));
  return resp.data;
}

export async function calculateTaxForProfile(
  taxProfileId: string,
): Promise<TaxCalculationResult> {
  const resp = await api.post<TaxCalculationResult>(
    `/tax-calculations/${taxProfileId}/calculate`,
  );
  return resp.data;
}

export async function previewTaxWorkspace(year: number): Promise<TaxWorkspacePreview> {
  const resp = await api.get<TaxWorkspacePreview>(`/tax-workspace/${year}`);
  return resp.data;
}

export async function saveTaxWorkspaceRun(year: number, expectedVersion: number): Promise<TaxWorkspaceRun> {
  const resp = await api.post<TaxWorkspaceRun>(`/tax-workspace/${year}/runs`, {
    expected_version: expectedVersion,
  });
  return resp.data;
}

export async function listTaxWorkspaceRuns(year: number): Promise<TaxWorkspaceRun[]> {
  const resp = await api.get<TaxWorkspaceRun[]>(`/tax-workspace/${year}/runs`);
  return resp.data;
}

export async function runAdvisor(
  taxProfileId: string,
  lang: AdvisorLang = "ar",
): Promise<AdvisorReport> {
  const resp = await api.post<AdvisorReport>(
    `/advisor/${taxProfileId}/run`,
    { lang },
    { timeout: 60_000, headers: usageRequestHeaders() },
  );
  return resp.data;
}

export async function getLatestAdvisorReport(
  taxProfileId: string,
): Promise<AdvisorLatestReport | null> {
  const resp = await api.get<AdvisorLatestReport | null>(
    `/advisor/${taxProfileId}/latest`,
  );
  return resp.data;
}

export async function createIncomeSource(
  payload: IncomeSourceCreate,
  expectedVersion?: number,
): Promise<IncomeSource> {
  const resp = await api.post<IncomeSource>("/income-sources/", payload, versionConfig(expectedVersion));
  return resp.data;
}

export async function listIncomeSources(
  taxProfileId: string,
): Promise<IncomeSource[]> {
  const resp = await api.get<IncomeSource[]>("/income-sources/", {
    params: { tax_profile_id: taxProfileId },
  });
  return resp.data;
}

export async function updateIncomeSource(
  id: string,
  payload: IncomeSourceUpdate,
  expectedVersion?: number,
): Promise<IncomeSource> {
  const resp = await api.put<IncomeSource>(`/income-sources/${id}`, payload, versionConfig(expectedVersion));
  return resp.data;
}

export async function deleteIncomeSource(id: string, expectedVersion?: number): Promise<void> {
  await api.delete(`/income-sources/${id}`, versionConfig(expectedVersion));
}

export async function createDeduction(
  payload: DeductionCreate,
  expectedVersion?: number,
): Promise<Deduction> {
  const resp = await api.post<Deduction>("/deductions/", payload, versionConfig(expectedVersion));
  return resp.data;
}

export async function listDeductions(
  taxProfileId: string,
): Promise<Deduction[]> {
  const resp = await api.get<Deduction[]>("/deductions/", {
    params: { tax_profile_id: taxProfileId },
  });
  return resp.data;
}

export async function updateDeduction(
  id: string,
  payload: DeductionUpdate,
  expectedVersion?: number,
): Promise<Deduction> {
  const resp = await api.put<Deduction>(`/deductions/${id}`, payload, versionConfig(expectedVersion));
  return resp.data;
}

export async function deleteDeduction(id: string, expectedVersion?: number): Promise<void> {
  await api.delete(`/deductions/${id}`, versionConfig(expectedVersion));
}

export async function sendChat(req: ChatRequest): Promise<ChatResponse> {
  const resp = await api.post<ChatResponse>("/rag/chat", req, {
    timeout: 60_000,
    headers: usageRequestHeaders(),
  });
  return resp.data;
}

/** Apply a confirmed in-chat "update your profile?" suggestion to the stored account. */
export async function applyChatUpdate(
  profileId: string,
  payload: ChatProfileUpdateApply,
  expectedVersion?: number,
): Promise<TaxProfile> {
  const resp = await api.post<TaxProfile>(
    `/tax-profiles/${profileId}/apply-chat-update`,
    payload,
    versionConfig(expectedVersion),
  );
  return resp.data;
}

export async function transcribeAudio(
  audio_b64: string,
  lang: "ar" | "en" = "ar",
  mime_type = "audio/wav",
): Promise<string> {
  const resp = await api.post<{ transcript: string }>(
    "/voice/transcribe",
    { audio_b64, lang, mime_type },
    { timeout: 60_000, headers: usageRequestHeaders() },
  );
  return resp.data.transcript;
}

export async function updateMe(payload: UserUpdatePayload): Promise<User> {
  const resp = await api.put<User>("/users/me", payload);
  return resp.data;
}

export async function getMyUsage(): Promise<UserUsage> {
  const resp = await api.get<UserUsage>("/users/me/usage");
  return resp.data;
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => item?.msg)
        .filter((msg): msg is string => typeof msg === "string")
        .join(" ");
    }
  }
  return fallback;
}

export async function getDocumentPreviewBlob(id: string): Promise<Blob> {
  const resp = await api.get(`/documents/${id}/preview`, {
    responseType: "blob",
  });
  return resp.data as Blob;
}

export type ProcessDocumentResult = {
  document_id: string;
  processing_status: "processed" | "failed";
  extracted_data: Record<string, unknown> | null;
  deduction_id: string | null;
};

export async function processDocument(
  documentId: string,
  taxProfileId?: string,
): Promise<ProcessDocumentResult> {
  const params = taxProfileId ? { tax_profile_id: taxProfileId } : undefined;
  const resp = await api.post<ProcessDocumentResult>(
    `/documents/${documentId}/process`,
    null,
    { params, headers: usageRequestHeaders() },
  );
  return resp.data;
}

export async function getExtractionDebug(
  documentId: string,
): Promise<ExtractionDebugResult> {
  const resp = await api.get<ExtractionDebugResult>(
    `/documents/${documentId}/extraction-debug`,
  );
  return resp.data;
}

export async function uploadAvatar(file: File): Promise<User> {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await api.post<User>("/users/me/avatar", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return resp.data;
}

export async function deleteAvatar(): Promise<User> {
  const resp = await api.delete<User>("/users/me/avatar");
  return resp.data;
}

export async function getCalendarEvents(year: number): Promise<CalendarEvent[]> {
  const resp = await api.get<CalendarEvent[]>("/calendar/events", {
    params: { year },
  });
  return resp.data;
}

export async function getNotifications(): Promise<NotificationItem[]> {
  const resp = await api.get<NotificationItem[]>("/notifications/");
  return resp.data;
}

// ── Chat History ────────────────────────────────────────────────────────────

export async function listChatSessions(): Promise<ChatSession[]> {
  const resp = await api.get<ChatSession[]>("/chat/sessions");
  return resp.data;
}

export async function getChatSession(id: string): Promise<ChatSessionWithMessages> {
  const resp = await api.get<ChatSessionWithMessages>(`/chat/sessions/${id}`);
  return resp.data;
}

export async function createChatSession(title?: string): Promise<ChatSession> {
  const resp = await api.post<ChatSession>(
    "/chat/sessions",
    title ? { title } : {},
  );
  return resp.data;
}

export async function renameChatSession(
  id: string,
  title: string,
): Promise<ChatSession> {
  const resp = await api.patch<ChatSession>(`/chat/sessions/${id}`, { title });
  return resp.data;
}

export async function deleteChatSession(id: string): Promise<void> {
  await api.delete(`/chat/sessions/${id}`);
}

export async function logChatMessage(
  sessionId: string,
  payload: ChatMessageCreatePayload,
): Promise<ChatMessage> {
  const resp = await api.post<ChatMessage>(
    `/chat/sessions/${sessionId}/messages`,
    payload,
  );
  return resp.data;
}

// ── Admin ───────────────────────────────────────────────────────────────────

export async function getAdminStats(): Promise<AdminStats> {
  const resp = await api.get<AdminStats>("/admin/stats");
  return resp.data;
}

export async function listAdminUsers(
  query: AdminUserListQuery = {},
): Promise<AdminUserList> {
  const resp = await api.get<AdminUserList>("/admin/users", { params: query });
  return resp.data;
}

export async function getAdminUser(id: string): Promise<AdminUserDetail> {
  const resp = await api.get<AdminUserDetail>(`/admin/users/${id}`);
  return resp.data;
}

export async function patchAdminUser(
  id: string,
  payload: AdminUserUpdate,
): Promise<AdminUserDetail> {
  const resp = await api.patch<AdminUserDetail>(`/admin/users/${id}`, payload);
  return resp.data;
}

export async function resetAdminUserUsage(
  id: string,
): Promise<AdminUserDetail> {
  const resp = await api.post<AdminUserDetail>(`/admin/users/${id}/usage/reset`);
  return resp.data;
}
