from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field
import uuid


# ==================== User Food Preferences (Long-Term Memory) ====================

class UserFoodPreferences(BaseModel):
    """Long-term user food preferences persisted across conversations.

    This model stores dietary restrictions, cuisine preferences, and other
    food-related preferences that should be remembered between sessions.
    """

    user_id: str

    # Dietary restrictions (vegetarian, vegan, gluten-free, halal, kosher, etc.)
    dietary_restrictions: list[str] = Field(default_factory=list)

    # Food allergies (nuts, shellfish, dairy, eggs, soy, etc.)
    allergies: list[str] = Field(default_factory=list)

    # Cuisine preferences (Italian, Mexican, Asian, etc.)
    favorite_cuisines: list[str] = Field(default_factory=list)
    disliked_cuisines: list[str] = Field(default_factory=list)

    # Specific food preferences
    favorite_foods: list[str] = Field(default_factory=list)
    disliked_foods: list[str] = Field(default_factory=list)

    # Spice tolerance (none, mild, medium, hot, extra_hot)
    spice_preference: Optional[Literal["none", "mild", "medium", "hot", "extra_hot"]] = None

    # Default budget preferences
    default_budget_per_person: Optional[float] = None
    preferred_price_level: Optional[Literal["$", "$$", "$$$", "$$$$"]] = None

    # Frequently ordered from (vendor IDs or names)
    favorite_vendors: list[str] = Field(default_factory=list)

    # Special notes (e.g., "prefers organic", "no MSG")
    notes: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def has_preferences(self) -> bool:
        """Check if user has any stored preferences."""
        return bool(
            self.dietary_restrictions or
            self.allergies or
            self.favorite_cuisines or
            self.disliked_cuisines or
            self.favorite_foods or
            self.disliked_foods or
            self.spice_preference or
            self.default_budget_per_person or
            self.preferred_price_level or
            self.favorite_vendors or
            self.notes
        )

    def get_summary(self) -> str:
        """Get a human-readable summary of preferences."""
        parts = []

        if self.dietary_restrictions:
            parts.append(f"Dietary: {', '.join(self.dietary_restrictions)}")
        if self.allergies:
            parts.append(f"Allergies: {', '.join(self.allergies)}")
        if self.favorite_cuisines:
            parts.append(f"Favorites: {', '.join(self.favorite_cuisines)}")
        if self.disliked_cuisines:
            parts.append(f"Avoids: {', '.join(self.disliked_cuisines)}")
        if self.spice_preference:
            parts.append(f"Spice: {self.spice_preference}")
        if self.default_budget_per_person:
            parts.append(f"Budget: ${self.default_budget_per_person}/person")

        return " | ".join(parts) if parts else "No preferences stored"


# ==================== Order Types ====================

# Order Types
OrderType = Literal["reservation", "catering", "doordash"]
OrderStatus = Literal["pending", "confirmed", "in_progress", "completed", "cancelled"]

# Food Order Workflow Steps
WorkflowStep = Literal[
    "gather_requirements",  # Collect headcount, date, budget, dietary
    "search_vendors",       # Find and present 3-5 vendor options
    "select_vendor",        # User chooses vendor
    "build_order",          # Configure menu items
    "review_order",         # Validate against constraints
    "confirm_order",        # Human approval
    "submit_order",         # API submission
    "track_order",          # Monitor status
]

# Food Order Delivery Status
DeliveryStatus = Literal[
    "draft",
    "pending_approval",
    "submitted",
    "accepted",
    "preparing",
    "dasher_confirmed",
    "picked_up",
    "in_transit",
    "delivered",
    "cancelled",
]

# Communication Log Statuses
CallStatus = Literal["initiated", "ringing", "in_progress", "completed", "failed", "no_answer"]
EmailStatus = Literal["draft", "sent", "delivered", "opened", "replied", "bounced"]
TextStatus = Literal["sent", "delivered", "read", "replied", "failed"]


class OrderItem(BaseModel):
    """An item in an order."""
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    quantity: int = 1
    price: float
    notes: Optional[str] = None


class CallLog(BaseModel):
    """A phone call log (Vapi)."""
    call_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vapi_call_id: Optional[str] = None
    direction: Literal["outbound", "inbound"] = "outbound"
    phone_number: str
    status: CallStatus = "initiated"
    duration: Optional[int] = None  # seconds
    transcript: Optional[str] = None
    summary: Optional[str] = None
    recording_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None


class EmailLog(BaseModel):
    """An email log."""
    email_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    direction: Literal["outbound", "inbound"] = "outbound"
    to_address: str
    from_address: str
    subject: str
    body: str
    status: EmailStatus = "draft"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None


class TextLog(BaseModel):
    """An SMS/text log."""
    text_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    direction: Literal["outbound", "inbound"] = "outbound"
    phone_number: str
    message: str
    status: TextStatus = "sent"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None


class Order(BaseModel):
    """A food order (reservation, catering, doordash)."""
    order_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chat_id: str  # Parent chat/conversation
    type: OrderType
    status: OrderStatus = "pending"

    # Vendor info
    vendor: str  # Restaurant/caterer name
    vendor_phone: Optional[str] = None
    vendor_email: Optional[str] = None
    vendor_address: Optional[str] = None

    # Event details
    event_date: str
    event_time: Optional[str] = None
    guest_count: int

    # Financial
    estimated_cost: Optional[float] = None
    actual_cost: Optional[float] = None
    items: list[OrderItem] = []

    # Communication logs
    calls: list[CallLog] = []
    emails: list[EmailLog] = []
    texts: list[TextLog] = []

    # Metadata
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Confirmation
    confirmation_number: Optional[str] = None
    confirmed_at: Optional[datetime] = None


class CateringQuote(BaseModel):
    """A quote from a catering service."""
    quote_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    caterer_name: str
    caterer_id: str
    items: list[OrderItem]
    subtotal: float
    tax: float
    delivery_fee: float
    total: float
    valid_until: datetime
    notes: Optional[str] = None


class Reservation(BaseModel):
    """A restaurant reservation."""
    reservation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_name: str
    restaurant_id: str
    party_size: int
    date: datetime
    time: str
    contact_name: str
    contact_email: str
    contact_phone: Optional[str] = None
    special_requests: Optional[str] = None
    status: Literal["pending", "confirmed", "cancelled"] = "pending"
    confirmation_number: Optional[str] = None


class PendingAction(BaseModel):
    """An action waiting for human approval."""
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_type: Literal["reservation", "catering_order", "doordash_order", "food_order", "poll_send", "call", "email", "text"]
    description: str
    payload: dict
    order_id: Optional[str] = None  # Link to parent order
    chat_id: Optional[str] = None  # Link to parent chat
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["pending", "approved", "rejected"] = "pending"
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class VendorOption(BaseModel):
    """A vendor option from search results."""
    vendor_id: str
    name: str
    rating: Optional[float] = None
    price_level: Optional[str] = None  # "$", "$$", "$$$"
    address: Optional[str] = None
    phone: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    source: Literal["yelp", "google"] = "yelp"
    distance: Optional[float] = None  # miles
    image_url: Optional[str] = None


class FoodOrderContext(BaseModel):
    """Tracks active food order through the workflow."""

    order_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Current workflow position
    current_step: WorkflowStep = "gather_requirements"
    completed_steps: list[WorkflowStep] = Field(default_factory=list)

    # Requirements (gathered in step 1)
    headcount: Optional[int] = None
    event_date: Optional[str] = None  # ISO format YYYY-MM-DD
    event_time: Optional[str] = None  # HH:MM format
    delivery_address: Optional[str] = None
    budget_total: Optional[float] = None
    budget_per_person: Optional[float] = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    cuisine_preferences: list[str] = Field(default_factory=list)

    # Vendor search results (step 2)
    vendor_options: list[VendorOption] = Field(default_factory=list)

    # Selected vendor (step 3)
    selected_vendor: Optional[VendorOption] = None

    # Order details (step 4)
    menu_items: list[OrderItem] = Field(default_factory=list)
    special_instructions: Optional[str] = None

    # Pricing (calculated in step 5)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    delivery_fee: Optional[float] = None
    service_fee: Optional[float] = None
    total: Optional[float] = None

    # Validation results (step 5)
    validation_errors: list[str] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)

    # DoorDash-specific fields
    doordash_quote_id: Optional[str] = None
    doordash_delivery_id: Optional[str] = None
    doordash_tracking_url: Optional[str] = None
    doordash_external_id: Optional[str] = None

    # Order lifecycle
    status: DeliveryStatus = "draft"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    submitted_at: Optional[datetime] = None
    estimated_pickup_time: Optional[datetime] = None
    estimated_delivery_time: Optional[datetime] = None
    actual_delivery_time: Optional[datetime] = None

    # Contact info for delivery
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    # Modification tracking
    modification_history: list[dict] = Field(default_factory=list)

    # Expense tracking (auto-generate expense on delivery)
    expense_provider: Optional[Literal["ramp", "brex", "csv"]] = None
    cost_splits: list[dict] = Field(default_factory=list)  # [{"team": "Eng", "pct": 60}]
    expense_id: Optional[str] = None  # ID from expense provider
    receipt_url: Optional[str] = None  # Firebase Storage URL

    # Calendar linkage
    calendar_event_id: Optional[str] = None
