"""SQLAlchemy models — leads, conversations, analytics, A/B tests."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Lead(Base):
    """Lead / prospect tracked through the funnel."""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    name = Column(String(255), default="")
    company = Column(String(255), default="")
    stage = Column(String(50), default="NEW_REPLY", index=True)
    thread_id = Column(String(100), default="", index=True)
    telegram_username = Column(String(100), default="")
    telegram_chat_id = Column(String(50), default="")
    notes = Column(Text, default="")
    follow_up_count = Column(Integer, default=0)
    account_email = Column(String(320), default="")  # for multi-account

    # Enrichment data
    website = Column(String(500), default="")
    industry = Column(String(100), default="")
    company_size = Column(String(50), default="")
    location = Column(String(255), default="")

    # Multichannel & role tracking
    source_channel = Column(String(30), default="email")    # email/telegram/telegram_mtproto/whatsapp/avito
    traffic_source = Column(String(50), default="unknown")  # cold_email/organic/avito_listing/referred
    assigned_role = Column(String(50), default="sales_manager")  # sales_manager/recruiter/consultant/support
    lead_score = Column(Integer, default=0)                 # 0-100 автоматически
    whatsapp_number = Column(String(30), default="")

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_contact_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    messages = relationship("Message", back_populates="lead", cascade="all, delete-orphan")
    ab_results = relationship("ABTestResult", back_populates="lead", cascade="all, delete-orphan")


class Message(Base):
    """Email/Telegram message log for analytics and feedback."""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    direction = Column(String(10), nullable=False)  # "inbound" or "outbound"
    channel = Column(String(20), default="email")  # "email" or "telegram"
    gmail_message_id = Column(String(100), default="")
    subject = Column(String(500), default="")
    body = Column(Text, default="")
    stage_at_time = Column(String(50), default="")
    classification = Column(String(50), default="")  # for inbound
    confidence = Column(Float, default=0.0)

    # A/B testing
    ab_variant = Column(String(10), default="")  # "A" or "B"

    # Role & traffic context
    role_used = Column(String(50), default="")
    traffic_source = Column(String(50), default="")

    # Attachment handling
    has_attachment = Column(Boolean, default=False)
    attachment_summary = Column(Text, default="")  # GPT-4o vision summary

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    lead = relationship("Lead", back_populates="messages")


class ABTestResult(Base):
    """A/B test tracking — which variant got a reply."""
    __tablename__ = "ab_test_results"

    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    stage = Column(String(50), nullable=False)
    variant_a = Column(Text, default="")
    variant_b = Column(Text, default="")
    sent_variant = Column(String(10), default="")  # "A" or "B"
    got_reply = Column(Boolean, default=False)
    reply_category = Column(String(50), default="")  # what the reply was classified as
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    lead = relationship("Lead", back_populates="ab_results")


class DailyStats(Base):
    """Daily aggregated stats for the dashboard."""
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True)
    date = Column(String(10), unique=True, nullable=False, index=True)  # YYYY-MM-DD
    emails_received = Column(Integer, default=0)
    emails_sent = Column(Integer, default=0)
    new_leads = Column(Integer, default=0)
    leads_interested = Column(Integer, default=0)
    leads_materials_sent = Column(Integer, default=0)
    leads_handoff = Column(Integer, default=0)
    leads_not_interested = Column(Integer, default=0)
    ab_tests_run = Column(Integer, default=0)
    ab_variant_a_wins = Column(Integer, default=0)
    ab_variant_b_wins = Column(Integer, default=0)


class RateLimit(Base):
    """Track daily send counts per email account."""
    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True)
    account_email = Column(String(320), nullable=False, index=True)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    send_count = Column(Integer, default=0)

    class Meta:
        unique_together = ("account_email", "date")
