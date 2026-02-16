from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid


class EventDetails(BaseModel):
    """Details about an office event or gathering."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    date: datetime
    headcount: int
    budget: Optional[float] = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    location: str
    event_type: str = "general"  # lunch, dinner, snacks, catering, meeting


class PollOption(BaseModel):
    """A single option in a poll."""

    option_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    votes: int = 0


class PollVote(BaseModel):
    """A vote cast in a poll."""

    voter_id: str
    option_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Poll(BaseModel):
    """An office poll for gathering preferences."""

    poll_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    options: list[PollOption]
    deadline: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    votes: list[PollVote] = Field(default_factory=list)
    webhook_url: Optional[str] = None
    is_closed: bool = False


class PollResults(BaseModel):
    """Aggregated results of a poll."""

    poll_id: str
    question: str
    total_votes: int
    results: dict[str, int]  # option_text -> vote_count
    winner: Optional[str] = None
    is_tie: bool = False
