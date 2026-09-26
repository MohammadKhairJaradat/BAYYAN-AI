from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from app.domain.money import format_legacy_amount, parse_money


MaritalStatusValue = Literal["single", "married"]
FilingStatusValue = Literal["individual", "joint"]
ResidencyStatusValue = Literal[
    "resident",
    "nonresident_jordanian",
    "nonresident_other",
]
IncomeTypeValue = Literal["salary", "freelance", "rental", "investment"]
DeductionCategoryValue = Literal[
    "medical",
    "education",
    "rent",
    "housing_interest",
    "housing_murabaha",
    "donations",
    "insurance",
    "pension",
]
# Who a documented expense is for. Display/tracking only — the tax engine pools
# deductions by category and ignores the beneficiary. Meaningful for medical /
# education; household categories (rent/housing/...) leave it null.
BeneficiaryValue = Literal["self", "spouse", "child"]


# ── Users ────────────────────────────────────────────────────────────────────


class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    phone: str | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    name: str
    phone: str | None
    created_at: dt.datetime
    is_active: bool
    is_admin: bool = False
    preferences: dict = {}
    avatar_url: str | None = None
    subscription_tier: str = "Basic"


class UserUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    preferences: dict | None = None


# ── Admin ──────────────────────────────────────────────────────────────────

TierName = Literal["Basic", "Pro", "Premium"]


class AdminUserRow(BaseModel):
    """Compact user row used in the admin /users list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    name: str
    created_at: dt.datetime
    is_active: bool
    is_admin: bool
    subscription_tier: str
    avatar_url: str | None = None


class AdminUserDetail(BaseModel):
    """Full admin view of a single user including current month usage."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    name: str
    phone: str | None
    created_at: dt.datetime
    is_active: bool
    is_admin: bool
    subscription_tier: str
    avatar_url: str | None = None
    usage_month: dt.date
    messages: UsageCounter
    docs: UsageCounter
    document_count: int
    tax_profile_count: int


class AdminUserUpdate(BaseModel):
    """PATCH body — every field optional; only set ones are applied."""

    subscription_tier: TierName | None = None
    is_active: bool | None = None


class AdminUserList(BaseModel):
    items: list[AdminUserRow]
    total: int
    page: int
    page_size: int


class AdminTierCount(BaseModel):
    tier: str
    count: int


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    inactive_users: int
    admins: int
    signups_this_month: int
    tier_counts: list[AdminTierCount]
    messages_this_month: int
    docs_this_month: int
    total_documents: int
    total_chat_sessions: int


class UsageCounter(BaseModel):
    used: int
    limit: int
    remaining: int


class AllowedModelRead(BaseModel):
    provider: str
    model: str


class UserUsageRead(BaseModel):
    tier: str
    usage_month: dt.date
    messages: UsageCounter
    docs: UsageCounter
    allowed_models: list[AllowedModelRead]
    max_tokens: int


# ── Tax Profiles ─────────────────────────────────────────────────────────────


class TaxProfileCreate(BaseModel):
    user_id: uuid.UUID
    tax_year: int = Field(..., ge=2000, le=2100)
    marital_status: MaritalStatusValue
    num_dependents: int = Field(0, ge=0, le=20)
    filing_status: FilingStatusValue | None = None
    residency_status: ResidencyStatusValue = "resident"
    claims_dependents_exemption: bool = False
    claim_spouse_expense_exemption: bool = False
    disability_exemption_count: int = Field(0, ge=0, le=20)


class TaxProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    tax_year: int
    version: int = 1
    marital_status: str
    num_dependents: int
    filing_status: str | None
    residency_status: str = "resident"
    claims_dependents_exemption: bool = False
    claim_spouse_expense_exemption: bool = False
    disability_exemption_count: int = 0
    created_at: dt.datetime


class TaxProfileUpdate(BaseModel):
    marital_status: MaritalStatusValue | None = None
    num_dependents: int | None = Field(default=None, ge=0, le=20)
    filing_status: FilingStatusValue | None = None
    residency_status: ResidencyStatusValue | None = None
    claims_dependents_exemption: bool | None = None
    claim_spouse_expense_exemption: bool | None = None
    disability_exemption_count: int | None = Field(default=None, ge=0, le=20)

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field in self.model_fields_set - {"filing_status"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


# ── Income Sources ───────────────────────────────────────────────────────────


class IncomeSourceCreate(BaseModel):
    tax_profile_id: uuid.UUID
    type: IncomeTypeValue
    amount: Decimal = Field(..., ge=Decimal("0"))
    tax_withheld: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    employer_name: str | None = None
    description: str | None = None

    @field_validator("amount", "tax_withheld")
    @classmethod
    def validate_money_precision(cls, value: Decimal) -> Decimal:
        return parse_money(value)


class IncomeSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tax_profile_id: uuid.UUID
    type: str
    amount: Decimal
    tax_withheld: Decimal = Decimal("0")
    employer_name: str | None
    description: str | None

    @field_serializer("amount", "tax_withheld", when_used="json")
    def serialize_money(self, value: Decimal) -> str:
        return format_legacy_amount(value)


class IncomeSourceUpdate(BaseModel):
    type: IncomeTypeValue | None = None
    amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    tax_withheld: Decimal | None = Field(default=None, ge=Decimal("0"))
    employer_name: str | None = None
    description: str | None = None

    @field_validator("amount", "tax_withheld")
    @classmethod
    def validate_money_precision(cls, value: Decimal | None) -> Decimal | None:
        return parse_money(value) if value is not None else None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field in self.model_fields_set & {"type", "amount", "tax_withheld"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


# ── Deductions ───────────────────────────────────────────────────────────────


class DeductionCreate(BaseModel):
    tax_profile_id: uuid.UUID
    category: DeductionCategoryValue
    amount: Decimal = Field(..., ge=Decimal("0"))
    date: dt.date | None = None
    description: str | None = None
    beneficiary: BeneficiaryValue | None = None
    beneficiary_name: str | None = None
    document_id: uuid.UUID | None = None

    @field_validator("amount")
    @classmethod
    def validate_money_precision(cls, value: Decimal) -> Decimal:
        return parse_money(value)


class DeductionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tax_profile_id: uuid.UUID
    category: str
    amount: Decimal
    date: dt.date | None
    description: str | None
    beneficiary: str | None
    beneficiary_name: str | None
    document_id: uuid.UUID | None

    @field_serializer("amount", when_used="json")
    def serialize_money(self, value: Decimal) -> str:
        return format_legacy_amount(value)


class DeductionUpdate(BaseModel):
    category: DeductionCategoryValue | None = None
    amount: Decimal | None = Field(default=None, ge=Decimal("0"))
    date: dt.date | None = None
    description: str | None = None
    beneficiary: BeneficiaryValue | None = None
    beneficiary_name: str | None = None
    document_id: uuid.UUID | None = None

    @field_validator("amount")
    @classmethod
    def validate_money_precision(cls, value: Decimal | None) -> Decimal | None:
        return parse_money(value) if value is not None else None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        for field in self.model_fields_set & {"category", "amount"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


# ── Documents ────────────────────────────────────────────────────────────────


class DocumentCreate(BaseModel):
    user_id: uuid.UUID
    document_type: str
    original_filename: str


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    file_path: str
    original_filename: str
    document_type: str
    upload_date: dt.datetime
    processing_status: str
    extracted_data: dict | None
    has_linked_deduction: bool = False


# ── Filing History ───────────────────────────────────────────────────────────


class FilingHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tax_profile_id: uuid.UUID
    total_income: Decimal | None
    total_deductions: Decimal | None
    taxable_income: Decimal | None
    tax_liability: Decimal | None
    filed_at: dt.datetime

    @field_serializer("total_income", "total_deductions", "taxable_income", "tax_liability", when_used="json")
    def serialize_money(self, value: Decimal | None) -> str | None:
        return format_legacy_amount(value) if value is not None else None


# ── Auth ────────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Tax Calculations ────────────────────────────────────────────────────────


class TaxCalculationResult(BaseModel):
    tax_profile_id: uuid.UUID
    gross_income: float
    personal_exemption: float
    family_exemption: float
    expense_exemption: float = 0.0
    disability_exemption: float = 0.0
    total_exemptions: float
    deductions_allowed: dict[str, float]
    deductions_disallowed: dict[str, float]
    total_deductions: float
    taxable_income: float
    bracket_breakdown: list[dict]
    national_contribution: float = 0.0
    tax_liability: float
    total_tax_withheld: float = 0.0
    net_tax_due: float = 0.0
    refund_due: float = 0.0
    effective_rate: float
    marginal_rate: float


class TaxBracketV2(BaseModel):
    from_: str = Field(alias="from", pattern=r"^\d+\.\d{3}$")
    to: str | None = None
    rate: str
    income: str
    tax: str


class TaxCalculationResultV2(BaseModel):
    """Exact-money demonstration response; the original float API stays available."""

    tax_profile_id: uuid.UUID
    tax_year: int
    ruleset_id: str
    official_filing: Literal[False]
    gross_income: str
    personal_exemption: str
    family_exemption: str
    expense_exemption: str
    disability_exemption: str
    total_exemptions: str
    deductions_allowed: dict[str, str]
    deductions_disallowed: dict[str, str]
    total_deductions: str
    taxable_income: str
    bracket_breakdown: list[TaxBracketV2]
    tax_before_rounding: str
    national_contribution: str
    tax_liability: str
    total_tax_withheld: str
    net_tax_due: str
    refund_due: str
    effective_rate: str
    marginal_rate: str


# ── Document Processing ─────────────────────────────────────────────────────


class DocumentProcessingResult(BaseModel):
    document_id: uuid.UUID
    processing_status: str
    extracted_data: dict | None
    deduction_id: uuid.UUID | None = None


class ExtractionDebugResult(BaseModel):
    document_id: uuid.UUID
    original_filename: str
    document_type: str
    processing_status: str
    upload_date: dt.datetime
    extracted_data: dict | None
    deduction: DeductionRead | None


# ── RAG ─────────────────────────────────────────────────────────────────────


class RAGQueryRequest(BaseModel):
    question: str
    top_k: int = 5
    source_type: str | None = None
    lang: str = "ar"


class RAGChunk(BaseModel):
    chunk_id: str
    text: str
    score: float
    citation: str
    metadata: dict


class RAGQueryResponse(BaseModel):
    chunks: list[RAGChunk]
    context: str


# ── Chat (qa.py LLM-answer endpoint) ────────────────────────────────────────


class ChatRequest(BaseModel):
    question: str
    provider: str | None = None  # anthropic | openai | gemini | groq
    model: str | None = None
    lang: str = "ar"
    session_id: uuid.UUID | None = None


class ChatSource(BaseModel):
    citation: str
    score: float | None = None
    kind: str | None = None
    label: str | None = None
    stale: bool | None = None
    updated_at: str | None = None
    tax_year: int | None = None


ProfileUpdateValue = float | int | str | bool | None


class ProfileUpdateOption(BaseModel):
    """One choice when a contradiction maps to several rows (e.g. many income sources)."""

    entity_id: uuid.UUID
    label: str
    current_value: ProfileUpdateValue = None


class ProfileUpdateSuggestion(BaseModel):
    """A chat-stated fact that contradicts the stored account, offered for confirm-and-write.

    Surfaced in ChatResponse; the user confirms via POST /tax-profiles/{id}/apply-chat-update.
    """

    entity: str  # "tax_profile" | "income_source" | "deduction"
    field: str  # e.g. "gross_income" | "marital_status" | "num_dependents" | "amount" | "employer_name"
    action: str  # "update" | "create" | "choose"
    label_ar: str
    label_en: str
    current_value: ProfileUpdateValue = None
    new_value: ProfileUpdateValue = None
    entity_id: uuid.UUID | None = None  # row to update; None for create / choose
    category: str | None = None  # deduction category, when relevant
    options: list[ProfileUpdateOption] = []  # for action == "choose"


class ChatProfileUpdateApply(BaseModel):
    """Confirmed write request from the in-chat update card."""

    entity: str  # "tax_profile" | "income_source" | "deduction"
    field: str
    action: str  # "update" | "create"
    new_value: ProfileUpdateValue = None
    entity_id: uuid.UUID | None = None
    category: str | None = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = []
    provider: str
    model: str | None = None
    tax_breakdown: dict | None = None
    profile_updates: list[ProfileUpdateSuggestion] = []
    profile_id: uuid.UUID | None = None  # owning profile for apply-chat-update
    session_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID


# ── Chat History (persisted sessions + messages) ────────────────────────────


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: str  # "user" | "assistant" | "system"
    kind: str  # "text" | "voice" | "upload"
    content: str
    sources: list[dict] | None = None
    tax_breakdown: dict | None = None
    provider: str | None = None
    model: str | None = None
    created_at: dt.datetime


class ChatSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ChatSessionWithMessages(ChatSessionRead):
    messages: list[ChatMessageRead] = []


class ChatSessionCreate(BaseModel):
    title: str | None = None


class ChatSessionUpdate(BaseModel):
    title: str


class ChatMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str  # Client logging is restricted to user messages.
    kind: str = "text"  # "text" | "voice" | "upload"
    content: str


# ── Calendar ────────────────────────────────────────────────────────────────


class CalendarEvent(BaseModel):
    date: dt.date
    title: str
    type: str  # "deadline" | "filing" | "reminder"
    description: str | None = None


# ── Notifications ───────────────────────────────────────────────────────────


class Notification(BaseModel):
    id: str
    title: str
    message: str
    severity: str  # "info" | "warning" | "action"
    link: str | None = None
    created_at: dt.datetime


# ── Advisor (LangGraph) ─────────────────────────────────────────────────────


class AdvisorRunRequest(BaseModel):
    lang: str = "ar"  # "ar" | "en"


class AdvisorScenario(BaseModel):
    label: str
    gross_income: float
    taxable_income: float
    tax_liability: float
    delta_vs_baseline: float
    effective_rate: float
    marginal_rate: float


class AdvisorDeductionOpportunity(BaseModel):
    category: str
    description: str
    estimated_savings: float | None = None
    citation: str | None = None


class AdvisorRiskFlag(BaseModel):
    severity: str  # "low" | "medium" | "high"
    issue: str
    suggestion: str | None = None


class AdvisorActionStep(BaseModel):
    priority: int
    action: str
    description: str | None = None


class AdvisorReport(BaseModel):
    tax_profile_id: uuid.UUID
    lang: str
    status: str  # "complete" | "incomplete"
    missing_fields: list[str] = []
    baseline: TaxCalculationResult | None = None
    scenarios: list[AdvisorScenario] = []
    deduction_opportunities: list[AdvisorDeductionOpportunity] = []
    risk_flags: list[AdvisorRiskFlag] = []
    action_plan: list[AdvisorActionStep] = []
    narratives: dict[str, str] = {}
    errors: list[str] = []


class AdvisorLatestReport(BaseModel):
    report: AdvisorReport
    input_fingerprint: str
    is_stale: bool
    updated_at: dt.datetime
