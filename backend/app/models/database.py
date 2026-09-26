import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ────────────────────────────────────────────────────────────────────


class MaritalStatus(str, enum.Enum):
    single = "single"
    married = "married"
    # Aliases — Python convention is UPPERCASE; tax_engine uses these names.
    SINGLE = "single"
    MARRIED = "married"


class FilingStatus(str, enum.Enum):
    individual = "individual"
    joint = "joint"
    INDIVIDUAL = "individual"
    JOINT = "joint"


class IncomeType(str, enum.Enum):
    salary = "salary"
    freelance = "freelance"
    rental = "rental"
    investment = "investment"
    SALARY = "salary"
    FREELANCE = "freelance"
    RENTAL = "rental"
    INVESTMENT = "investment"


class DeductionCategory(str, enum.Enum):
    medical = "medical"
    education = "education"
    rent = "rent"
    housing_interest = "housing_interest"
    housing_murabaha = "housing_murabaha"
    donations = "donations"
    insurance = "insurance"
    pension = "pension"
    MEDICAL = "medical"
    EDUCATION = "education"
    RENT = "rent"
    HOUSING_INTEREST = "housing_interest"
    HOUSING_MURABAHA = "housing_murabaha"
    DONATIONS = "donations"
    INSURANCE = "insurance"
    PENSION = "pension"


class DocumentType(str, enum.Enum):
    receipt = "receipt"
    salary_slip = "salary_slip"
    bank_statement = "bank_statement"
    RECEIPT = "receipt"
    SALARY_SLIP = "salary_slip"
    BANK_STATEMENT = "bank_statement"


class ProcessingStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    failed = "failed"
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


# ── Models ───────────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subscription_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Basic", server_default="Basic"
    )

    tax_profiles: Mapped[list["TaxProfile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    monthly_usage: Mapped[list["MonthlyUsage"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    advisor_reports: Mapped[list["AdvisorReportSnapshot"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshSession(Base):
    __tablename__ = "refresh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    target_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MonthlyUsage(Base):
    __tablename__ = "monthly_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_month", name="uq_monthly_usage_user_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    usage_month: Mapped[date] = mapped_column(Date, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="monthly_usage")


class UsageReservation(Base):
    __tablename__ = "usage_reservations"
    __table_args__ = (
        UniqueConstraint("user_id", "operation", "idempotency_key", name="uq_usage_reservation_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    usage_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="reserved")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    upload_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processing_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )
    extracted_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    user: Mapped["User"] = relationship(back_populates="documents")
    deductions: Mapped[list["Deduction"]] = relationship(back_populates="document")


class TaxProfile(Base):
    __tablename__ = "tax_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "tax_year", name="uq_user_tax_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    marital_status: Mapped[str] = mapped_column(String(20), nullable=False)
    num_dependents: Mapped[int] = mapped_column(Integer, default=0)
    filing_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    residency_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="resident", server_default="resident"
    )
    claims_dependents_exemption: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    claim_spouse_expense_exemption: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    disability_exemption_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="tax_profiles")
    income_sources: Mapped[list["IncomeSource"]] = relationship(
        back_populates="tax_profile", cascade="all, delete-orphan"
    )
    deductions: Mapped[list["Deduction"]] = relationship(
        back_populates="tax_profile", cascade="all, delete-orphan"
    )
    filing_history: Mapped[list["FilingHistory"]] = relationship(
        back_populates="tax_profile", cascade="all, delete-orphan"
    )
    advisor_report: Mapped["AdvisorReportSnapshot | None"] = relationship(
        back_populates="tax_profile", cascade="all, delete-orphan", uselist=False
    )


class IncomeSource(Base):
    __tablename__ = "income_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tax_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_profiles.id"),
        index=True,
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    tax_withheld: Mapped[Decimal] = mapped_column(
        Numeric(15, 3), nullable=False, default=0, server_default="0"
    )
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    tax_profile: Mapped["TaxProfile"] = relationship(
        back_populates="income_sources"
    )


class Deduction(Base):
    __tablename__ = "deductions"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_deductions_document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tax_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_profiles.id"),
        index=True,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 3), nullable=False)
    date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Display/tracking only — who the expense is for (self|spouse|child) and an
    # optional free-text name (e.g. a child's name). Ignored by the tax engine,
    # which pools deductions by category; see tax_engine.calculate_exemptions.
    beneficiary: Mapped[str | None] = mapped_column(String(20), nullable=True)
    beneficiary_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id"),
        index=True,
        nullable=True,
    )

    tax_profile: Mapped["TaxProfile"] = relationship(
        back_populates="deductions"
    )
    document: Mapped["Document | None"] = relationship(
        back_populates="deductions"
    )


class FilingHistory(Base):
    __tablename__ = "filing_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tax_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_profiles.id"),
        index=True,
        nullable=False,
    )
    total_income: Mapped[Decimal | None] = mapped_column(Numeric(15, 3), nullable=True)
    total_deductions: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 3), nullable=True
    )
    taxable_income: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 3), nullable=True
    )
    tax_liability: Mapped[Decimal | None] = mapped_column(
        Numeric(15, 3), nullable=True
    )
    filed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tax_profile: Mapped["TaxProfile"] = relationship(
        back_populates="filing_history"
    )


class CalculationRun(Base):
    """Saved immutable demonstration calculation; no update/delete API exists."""

    __tablename__ = "calculation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tax_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tax_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ruleset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    input_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False,
    )


class AdvisorReportSnapshot(Base):
    __tablename__ = "advisor_reports"
    __table_args__ = (
        UniqueConstraint(
            "tax_profile_id", name="uq_advisor_reports_tax_profile_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    tax_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tax_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    lang: Mapped[str] = mapped_column(String(2), nullable=False)
    report: Mapped[dict] = mapped_column(JSONB, nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="advisor_reports")
    tax_profile: Mapped["TaxProfile"] = relationship(
        back_populates="advisor_report"
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(120), nullable=False, default="New chat"
    )
    memory_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    memory_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tax_breakdown: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")
