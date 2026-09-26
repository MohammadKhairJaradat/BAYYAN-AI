export interface User {
  id: string;
  username: string;
  name: string;
  phone: string | null;
  created_at: string;
  is_active: boolean;
  is_admin: boolean;
  preferences: Record<string, unknown>;
  avatar_url: string | null;
  subscription_tier: SubscriptionTier;
}

// ── Admin ───────────────────────────────────────────────────────────────────

export interface AdminUserRow {
  id: string;
  username: string;
  name: string;
  created_at: string;
  is_active: boolean;
  is_admin: boolean;
  subscription_tier: SubscriptionTier;
  avatar_url: string | null;
}

export interface AdminUserList {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminUserDetail {
  id: string;
  username: string;
  name: string;
  phone: string | null;
  created_at: string;
  is_active: boolean;
  is_admin: boolean;
  subscription_tier: SubscriptionTier;
  avatar_url: string | null;
  usage_month: string;
  messages: UsageCounter;
  docs: UsageCounter;
  document_count: number;
  tax_profile_count: number;
}

export interface AdminUserUpdate {
  subscription_tier?: SubscriptionTier;
  is_active?: boolean;
}

export interface AdminUserListQuery {
  q?: string;
  tier?: SubscriptionTier;
  active?: boolean;
  page?: number;
  page_size?: number;
}

export interface AdminTierCount {
  tier: string;
  count: number;
}

export interface AdminStats {
  total_users: number;
  active_users: number;
  inactive_users: number;
  admins: number;
  signups_this_month: number;
  tier_counts: AdminTierCount[];
  messages_this_month: number;
  docs_this_month: number;
  total_documents: number;
  total_chat_sessions: number;
}

export type SubscriptionTier = "Basic" | "Pro" | "Premium";

export interface TierCapability {
  name: SubscriptionTier;
  max_messages_per_month: number;
  max_docs_per_month: number;
  max_tokens: number;
  max_extractions_per_month: number;
  max_advisor_runs_per_month: number;
  max_voice_clips_per_month: number;
  allowed_models: AllowedModelRead[];
}

export interface PublicCapabilities {
  product: "BAYYAN";
  tier_changes: "admin_only";
  official_filing: false;
  legal_corpus: "demo";
  ai: {
    configured_providers: ChatProvider[];
    document_extraction: boolean;
    advisor: boolean;
    voice: boolean;
  };
  tiers: TierCapability[];
}

export interface UserUpdatePayload {
  name?: string;
  phone?: string | null;
  preferences?: Record<string, unknown>;
}

export interface SignupRequest {
  username: string;
  password: string;
  name: string;
  phone?: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface ApiError {
  detail: string;
}

export interface UsageCounter {
  used: number;
  limit: number;
  remaining: number;
}

export interface AllowedModelRead {
  provider: ChatProvider;
  model: string;
}

export interface UserUsage {
  tier: SubscriptionTier;
  usage_month: string;
  messages: UsageCounter;
  docs: UsageCounter;
  allowed_models: AllowedModelRead[];
  max_tokens: number;
}

// ── Tax Profiles ─────────────────────────────────────────────────────────────

export type MaritalStatus = "single" | "married";
export type ResidencyStatus =
  | "resident"
  | "nonresident_jordanian"
  | "nonresident_other";
export type FilingStatus = "individual" | "joint";

export interface TaxProfile {
  id: string;
  user_id: string;
  tax_year: number;
  version: number;
  marital_status: MaritalStatus;
  num_dependents: number;
  filing_status: FilingStatus | null;
  residency_status: ResidencyStatus;
  claims_dependents_exemption: boolean;
  claim_spouse_expense_exemption: boolean;
  disability_exemption_count: number;
  created_at: string;
}

export interface TaxProfileCreate {
  user_id: string;
  tax_year: number;
  marital_status: MaritalStatus;
  num_dependents: number;
  filing_status?: FilingStatus | null;
  residency_status?: ResidencyStatus;
  claims_dependents_exemption?: boolean;
  claim_spouse_expense_exemption?: boolean;
  disability_exemption_count?: number;
}

export interface TaxProfileUpdate {
  marital_status?: MaritalStatus;
  num_dependents?: number;
  filing_status?: FilingStatus | null;
  residency_status?: ResidencyStatus;
  claims_dependents_exemption?: boolean;
  claim_spouse_expense_exemption?: boolean;
  disability_exemption_count?: number;
}

// ── Income Sources ───────────────────────────────────────────────────────────

export type IncomeType = "salary" | "freelance" | "rental" | "investment";
export type DeductionCategory =
  | "medical"
  | "education"
  | "rent"
  | "housing_interest"
  | "housing_murabaha"
  | "donations"
  | "insurance"
  | "pension";

// Who a documented expense is for. Display/tracking only — the tax engine pools
// deductions by category and ignores this. Meaningful for medical/education.
export type BeneficiaryType = "self" | "spouse" | "child";

// Categories where attributing the expense to a person makes sense.
export const BENEFICIARY_CATEGORIES: DeductionCategory[] = ["medical", "education"];

export interface IncomeSourceCreate {
  tax_profile_id: string;
  type: IncomeType;
  amount: number | string;
  tax_withheld?: number | string;
  employer_name?: string | null;
  description?: string | null;
}

export interface IncomeSource extends IncomeSourceCreate {
  id: string;
  amount: number | string;
  tax_withheld: number | string;
}

export interface IncomeSourceUpdate {
  type?: IncomeType;
  amount?: number | string;
  tax_withheld?: number | string;
  employer_name?: string | null;
  description?: string | null;
}

export interface DeductionCreate {
  tax_profile_id: string;
  category: DeductionCategory;
  amount: number | string;
  date?: string | null;
  description?: string | null;
  beneficiary?: BeneficiaryType | null;
  beneficiary_name?: string | null;
  document_id?: string | null;
}

export interface Deduction extends DeductionCreate {
  id: string;
}

export interface DeductionUpdate {
  category?: DeductionCategory;
  amount?: number | string;
  date?: string | null;
  description?: string | null;
  beneficiary?: BeneficiaryType | null;
  beneficiary_name?: string | null;
  document_id?: string | null;
}

// ── Document extraction debug ────────────────────────────────────────────────

export interface ExtractedDataPayload {
  vendor?: string | null;
  amount?: number | null;
  date?: string | null;
  category?: string;
  document_type?: string;
  confidence?: number;
  raw_text?: string | null;
  extras?: Record<string, unknown>;
  extractor_backend?: string;
  error?: string | null;
  user_type_corrected_from?: string;
  [k: string]: unknown;
}

export interface ExtractionDebugResult {
  document_id: string;
  original_filename: string;
  document_type: string;
  processing_status: string;
  upload_date: string;
  extracted_data: ExtractedDataPayload | null;
  deduction: Deduction | null;
}


// ── Advisor ──────────────────────────────────────────────────────────────────

export type AdvisorLang = "ar" | "en";

export interface AdvisorScenario {
  label: string;
  gross_income: number;
  taxable_income: number;
  tax_liability: number;
  delta_vs_baseline: number;
  effective_rate: number;
  marginal_rate: number;
}

export interface AdvisorDeductionOpportunity {
  category: string;
  description: string;
  estimated_savings: number | null;
  citation: string | null;
}

export interface AdvisorRiskFlag {
  severity: "low" | "medium" | "high";
  issue: string;
  suggestion: string | null;
}

export interface AdvisorActionStep {
  priority: number;
  action: string;
  description: string | null;
}

export interface BracketBreakdownRow {
  from: number;
  to: number | null;
  rate: number;
  taxable_in_bracket: number;
  tax_in_bracket: number;
}

export interface TaxCalculationResult {
  tax_profile_id: string;
  gross_income: number;
  personal_exemption: number;
  family_exemption: number;
  expense_exemption: number;
  disability_exemption: number;
  total_exemptions: number;
  deductions_allowed: Record<string, number>;
  deductions_disallowed: Record<string, number>;
  total_deductions: number;
  taxable_income: number;
  bracket_breakdown: BracketBreakdownRow[];
  national_contribution: number;
  tax_liability: number;
  total_tax_withheld: number;
  net_tax_due: number;
  refund_due: number;
  effective_rate: number;
  marginal_rate: number;
}

export interface TaxWorkspaceRun {
  id: string;
  tax_profile_id: string | null;
  tax_year: number;
  profile_version: number;
  ruleset_id: string;
  input_fingerprint: string;
  input_snapshot: Record<string, unknown>;
  output_snapshot: Record<string, unknown>;
  created_at: string;
  stale: boolean;
}

export interface TaxWorkspacePreview {
  tax_year: number;
  profile_id: string;
  profile_version: number;
  input_snapshot: Record<string, unknown>;
  preview: Record<string, unknown>;
  latest_run: TaxWorkspaceRun | null;
}

export interface AdvisorReport {
  tax_profile_id: string;
  lang: AdvisorLang;
  status: "complete" | "incomplete";
  missing_fields: string[];
  baseline: TaxCalculationResult | null;
  scenarios: AdvisorScenario[];
  deduction_opportunities: AdvisorDeductionOpportunity[];
  risk_flags: AdvisorRiskFlag[];
  action_plan: AdvisorActionStep[];
  narratives: Record<"deductions" | "risk" | "plan", string>;
  errors: string[];
}

export interface AdvisorLatestReport {
  report: AdvisorReport;
  input_fingerprint: string;
  is_stale: boolean;
  updated_at: string;
}

// ── Chat (qa.py LLM-answer endpoint) ────────────────────────────────────────

export type ChatProvider = "anthropic" | "openai" | "gemini" | "groq";

export interface ChatRequest {
  question: string;
  provider?: ChatProvider | null;
  model?: string | null;
  lang?: "ar" | "en";
  session_id?: string | null;
}

export interface ChatSource {
  citation: string;
  score?: number | null;
  kind?: string | null;
  label?: string | null;
  stale?: boolean | null;
  updated_at?: string | null;
  tax_year?: number | null;
}

export type ProfileUpdateValue = number | string | boolean | null;

export interface ProfileUpdateOption {
  entity_id: string;
  label: string;
  current_value?: ProfileUpdateValue;
}

export interface ProfileUpdateSuggestion {
  entity: "tax_profile" | "income_source" | "deduction";
  field: string;
  action: "update" | "create" | "choose";
  label_ar: string;
  label_en: string;
  current_value?: ProfileUpdateValue;
  new_value?: ProfileUpdateValue;
  entity_id?: string | null;
  category?: string | null;
  options?: ProfileUpdateOption[];
}

export interface ChatProfileUpdateApply {
  entity: string;
  field: string;
  action: "update" | "create";
  new_value?: ProfileUpdateValue;
  entity_id?: string | null;
  category?: string | null;
}

export interface ChatResponse {
  answer: string;
  sources: ChatSource[];
  provider: string;
  model?: string | null;
  tax_breakdown?: Record<string, unknown> | null;
  profile_updates?: ProfileUpdateSuggestion[];
  profile_id?: string | null;
  session_id: string;
  user_message_id: string;
  assistant_message_id: string;
}

// ── Chat History (persisted) ────────────────────────────────────────────────

export type ChatRole = "user" | "assistant" | "system";
export type ChatKind = "text" | "voice" | "upload";

export interface ChatMessage {
  id: string;
  session_id: string;
  role: ChatRole;
  kind: ChatKind;
  content: string;
  sources?: ChatSource[] | null;
  tax_breakdown?: Record<string, unknown> | null;
  provider?: string | null;
  model?: string | null;
  created_at: string;
  // Transient (live-turn only; not persisted): in-chat "update your profile?" offers.
  profile_updates?: ProfileUpdateSuggestion[] | null;
  profile_id?: string | null;
}

export interface ChatSession {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatSessionWithMessages extends ChatSession {
  messages: ChatMessage[];
}

export interface ChatMessageCreatePayload {
  role: "user";
  kind?: ChatKind;
  content: string;
}

// ── Calendar ────────────────────────────────────────────────────────────────

export type CalendarEventType = "deadline" | "filing" | "reminder";

export interface CalendarEvent {
  date: string; // ISO yyyy-mm-dd
  title: string;
  type: CalendarEventType;
  description?: string | null;
}

// ── Notifications ───────────────────────────────────────────────────────────

export type NotificationSeverity = "info" | "warning" | "action";

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  severity: NotificationSeverity;
  link?: string | null;
  created_at: string;
}
