"""Data models for Slack, Google Calendar, and Expense integrations."""

import uuid
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field

from models.orders import OrderItem


# ==================== Slack Models ====================

class SlackContext(BaseModel):
    """Slack-specific context for routing agent responses back to Slack."""

    team_id: str
    channel_id: str
    user_id: str  # Slack user ID
    response_url: Optional[str] = None
    message_ts: Optional[str] = None  # For updating existing messages
    thread_ts: Optional[str] = None  # Thread parent timestamp
    finance_channel_id: Optional[str] = None  # Channel for receipt posting
    firebase_user_id: Optional[str] = None  # Linked Edesia account


class SlackInstallation(BaseModel):
    """Slack workspace installation record."""

    team_id: str
    team_name: str
    bot_token: str
    installing_user_id: str
    finance_channel_id: Optional[str] = None
    default_order_channel_id: Optional[str] = None
    approval_threshold: float = 500.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SlackUserLink(BaseModel):
    """Links a Slack user to a Firebase/Edesia user."""

    slack_user_id: str
    firebase_user_id: str
    team_id: str
    linked_at: datetime = Field(default_factory=datetime.utcnow)


class SlackSession(BaseModel):
    """Maps a Slack channel to a LangGraph session."""

    team_id: str
    channel_id: str
    session_id: str  # LangGraph thread_id
    firebase_user_id: Optional[str] = None
    slack_user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: datetime = Field(default_factory=datetime.utcnow)


# ==================== Google Calendar Models ====================

class CalendarEvent(BaseModel):
    """A Google Calendar event with attendee and location info."""

    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None  # Room name or street address
    attendee_emails: list[str] = Field(default_factory=list)
    organizer_email: Optional[str] = None
    description: Optional[str] = None


class AttendeeReport(BaseModel):
    """Aggregated dietary info across all meeting attendees."""

    headcount: int
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    per_attendee: dict[str, dict] = Field(default_factory=dict)  # email -> {name, restrictions, allergies}
    unknown_attendees: list[str] = Field(default_factory=list)  # Emails not in our system


# ==================== Expense Models ====================

class ExpenseEntry(BaseModel):
    """An expense entry for accounting/reimbursement."""

    expense_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: str
    vendor_name: str
    amount: float
    currency: str = "USD"
    category: str = "Meals & Entertainment"
    description: str
    date: str  # YYYY-MM-DD
    attendees: list[str] = Field(default_factory=list)
    cost_center: Optional[str] = None
    receipt_url: Optional[str] = None
    provider: Literal["ramp", "brex", "csv"] = "csv"
    status: Literal["draft", "submitted", "approved", "rejected"] = "draft"


class CostSplit(BaseModel):
    """A cost center split for dividing an order across teams."""

    team: str
    percentage: float  # 0-100
    amount: Optional[float] = None  # Calculated from percentage * total


class ReceiptData(BaseModel):
    """Structured receipt data for PDF generation and expense attachment."""

    order_id: str
    vendor_name: str
    items: list[OrderItem] = Field(default_factory=list)
    subtotal: float
    tax: float
    delivery_fee: float
    tip: float = 0.0
    total: float
    payment_method: str  # e.g. "Visa ending 4242"
    date: str  # YYYY-MM-DD
    attendee_count: int
    per_person_cost: float
