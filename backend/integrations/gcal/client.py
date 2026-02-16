"""Google Calendar API client operations."""

import logging
from typing import Optional
from datetime import datetime, timedelta

from googleapiclient.discovery import build
from models.integrations import CalendarEvent

logger = logging.getLogger(__name__)


def _get_service(credentials):
    """Build a Google Calendar API service object."""
    return build("calendar", "v3", credentials=credentials)


async def get_event_details(user_id: str, event_id: str) -> Optional[CalendarEvent]:
    """Fetch a single calendar event with attendees and location.

    Args:
        user_id: Firebase user ID (for credential lookup).
        event_id: Google Calendar event ID.

    Returns:
        CalendarEvent with attendees, location, and time details.
    """
    from integrations.gcal.auth import get_credentials

    creds = await get_credentials(user_id)
    if not creds:
        return None

    service = _get_service(creds)
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    return _parse_event(event)


async def list_upcoming_events(user_id: str, hours_ahead: int = 48) -> list[CalendarEvent]:
    """List upcoming calendar events.

    Args:
        user_id: Firebase user ID.
        hours_ahead: How far ahead to look (default 48 hours).

    Returns:
        List of upcoming CalendarEvent objects.
    """
    from integrations.gcal.auth import get_credentials

    creds = await get_credentials(user_id)
    if not creds:
        return []

    service = _get_service(creds)

    now = datetime.utcnow()
    time_max = now + timedelta(hours=hours_ahead)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat() + "Z",
        timeMax=time_max.isoformat() + "Z",
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    return [_parse_event(e) for e in events if e.get("start", {}).get("dateTime")]


async def create_lunch_event(
    user_id: str,
    vendor_name: str,
    delivery_time: str,
    headcount: int,
    attendee_emails: list[str],
    delivery_address: Optional[str] = None,
) -> Optional[str]:
    """Create a 'Lunch Order' calendar event when an order is confirmed.

    Args:
        user_id: Firebase user ID.
        vendor_name: Restaurant/vendor name.
        delivery_time: ISO datetime string for delivery.
        headcount: Number of people.
        attendee_emails: List of attendee email addresses.
        delivery_address: Optional delivery location.

    Returns:
        Created event ID, or None on failure.
    """
    from integrations.gcal.auth import get_credentials

    creds = await get_credentials(user_id)
    if not creds:
        return None

    service = _get_service(creds)

    # Parse delivery time
    try:
        dt = datetime.fromisoformat(delivery_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        dt = datetime.utcnow() + timedelta(hours=1)

    end_time = dt + timedelta(minutes=45)  # 45-min lunch window

    event = {
        "summary": f"Lunch Order: {vendor_name}",
        "description": f"Order from {vendor_name} for {headcount} people.\nOrdered via Edesia.",
        "start": {"dateTime": dt.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        "attendees": [{"email": email} for email in attendee_emails[:50]],
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 30},
                {"method": "popup", "minutes": 10},
            ],
        },
    }

    if delivery_address:
        event["location"] = delivery_address

    try:
        created = service.events().insert(
            calendarId="primary",
            body=event,
            sendUpdates="all",
        ).execute()
        return created.get("id")
    except Exception as e:
        logger.error(f"Failed to create lunch event: {e}")
        return None


async def add_reminder_to_event(
    user_id: str,
    event_id: str,
    minutes_before: int = 30,
) -> bool:
    """Add a popup reminder to an existing calendar event.

    Args:
        user_id: Firebase user ID.
        event_id: Google Calendar event ID.
        minutes_before: Minutes before event to trigger reminder.

    Returns:
        True if reminder added successfully.
    """
    from integrations.gcal.auth import get_credentials

    creds = await get_credentials(user_id)
    if not creds:
        return False

    service = _get_service(creds)

    try:
        event = service.events().get(calendarId="primary", eventId=event_id).execute()

        # Merge with existing reminders
        reminders = event.get("reminders", {})
        overrides = reminders.get("overrides", [])

        # Avoid duplicates
        existing_minutes = {r.get("minutes") for r in overrides}
        if minutes_before not in existing_minutes:
            overrides.append({"method": "popup", "minutes": minutes_before})

        event["reminders"] = {"useDefault": False, "overrides": overrides}

        service.events().update(
            calendarId="primary",
            eventId=event_id,
            body=event,
        ).execute()

        return True
    except Exception as e:
        logger.error(f"Failed to add reminder: {e}")
        return False


def _parse_event(event: dict) -> CalendarEvent:
    """Parse a Google Calendar API event into a CalendarEvent model."""
    start = event.get("start", {})
    end = event.get("end", {})

    # Handle all-day vs timed events
    start_time = start.get("dateTime", start.get("date", ""))
    end_time = end.get("dateTime", end.get("date", ""))

    # Parse datetime strings
    try:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        start_dt = datetime.utcnow()

    try:
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        end_dt = start_dt + timedelta(hours=1)

    attendees = event.get("attendees", [])
    attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]

    organizer = event.get("organizer", {})

    return CalendarEvent(
        event_id=event.get("id", ""),
        title=event.get("summary", ""),
        start_time=start_dt,
        end_time=end_dt,
        location=event.get("location"),
        attendee_emails=attendee_emails,
        organizer_email=organizer.get("email"),
        description=event.get("description"),
    )
