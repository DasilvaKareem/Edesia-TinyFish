"""Agent state schema for LangGraph."""

from typing import Annotated, Optional, TypedDict, Literal, Union
from langgraph.graph.message import add_messages

from models.events import EventDetails, PollResults
from models.orders import PendingAction, FoodOrderContext, WorkflowStep, UserFoodPreferences


class AgentState(TypedDict):
    """State schema for the Edesia agent graph."""

    # Conversation messages (automatically merged by LangGraph)
    messages: Annotated[list, add_messages]

    # Current event being planned (if any)
    event_details: Optional[EventDetails]

    # Actions awaiting human approval
    pending_actions: list[dict]

    # Poll results (when analyzing polls)
    poll_results: Optional[PollResults]

    # Current plan for multi-step tasks
    current_plan: Optional[str]

    # Router classification
    intent: Optional[Literal[
        "reservation", "catering", "delivery", "poll", "budget",
        "nutrition", "voice_call", "browser", "location", "general",
        "food_order"  # New intent for food ordering workflow
    ]]

    # Whether we need human approval before proceeding
    needs_approval: bool

    # Session ID for tracking
    session_id: Optional[str]

    # User ID for long-term preference storage
    user_id: Optional[str]

    # Food order workflow tracking
    food_order: Optional[FoodOrderContext]

    # For "jump anywhere" functionality - user can request specific step
    requested_step: Optional[WorkflowStep]

    # Cached vendor search results (for re-presenting options)
    cached_vendor_search: Optional[dict]

    # Long-term user food preferences (loaded from Redis)
    user_preferences: Optional[dict]

    # Flag to indicate preferences were updated this turn
    preferences_updated: bool

    # User's timezone (e.g., 'America/New_York')
    timezone: Optional[str]

    # User's company profile (from onboarding)
    user_profile: Optional[dict]

    # Flag indicating the current message contains images for vision processing
    has_images: bool

    # Chat ID for Firestore order tracking (POEM loop)
    chat_id: Optional[str]

    # Source channel: where the conversation originated
    source_channel: Optional[Literal["web", "slack", "calendar"]]

    # Slack-specific context (only populated when source_channel == "slack")
    slack_context: Optional[dict]


def create_initial_state(
    messages: list = None,
    session_id: str = None,
    user_id: str = None,
    user_preferences: dict = None,
    timezone: str = None,
    user_profile: dict = None,
    has_images: bool = False,
    chat_id: str = None,
    source_channel: str = None,
    slack_context: dict = None,
) -> AgentState:
    """Create an initial agent state.

    Args:
        messages: Initial conversation messages.
        session_id: Conversation session ID.
        user_id: User ID for preference lookup.
        user_preferences: Pre-loaded user preferences (from Redis).
        timezone: User's timezone (e.g., 'America/New_York').
        user_profile: User's company profile (from onboarding).
        has_images: Whether the message contains images for vision processing.
        chat_id: Firestore chat ID for POEM loop order tracking.
        source_channel: Origin of the conversation ("web", "slack", "calendar").
        slack_context: Slack-specific routing context (serialized SlackContext).
    """
    return {
        "messages": messages or [],
        "event_details": None,
        "pending_actions": [],
        "poll_results": None,
        "current_plan": None,
        "intent": None,
        "needs_approval": False,
        "session_id": session_id,
        "user_id": user_id,
        "food_order": None,
        "requested_step": None,
        "cached_vendor_search": None,
        "user_preferences": user_preferences,
        "preferences_updated": False,
        "timezone": timezone,
        "user_profile": user_profile,
        "has_images": has_images,
        "chat_id": chat_id,
        "source_channel": source_channel,
        "slack_context": slack_context,
    }
