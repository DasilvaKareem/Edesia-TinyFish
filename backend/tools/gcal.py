"""Google Calendar LangGraph tools for the Edesia agent."""

from typing import Optional
from langchain_core.tools import tool


@tool
def get_calendar_event(user_id: str, event_id: str) -> dict:
    """
    Get details for a specific calendar event including attendees and location.

    Args:
        user_id: The user's Firebase UID
        event_id: Google Calendar event ID

    Returns:
        Event details with attendees, location, time, and description
    """
    import asyncio
    from integrations.gcal.client import get_event_details

    try:
        event = asyncio.get_event_loop().run_until_complete(
            get_event_details(user_id, event_id)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        event = loop.run_until_complete(get_event_details(user_id, event_id))
        loop.close()

    if not event:
        return {"error": "Event not found or calendar not connected. Ask the user to connect Google Calendar in Settings."}

    return {
        "event_id": event.event_id,
        "title": event.title,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "location": event.location,
        "attendee_count": len(event.attendee_emails),
        "attendee_emails": event.attendee_emails,
        "organizer": event.organizer_email,
        "description": event.description,
    }


@tool
def list_upcoming_meetings(user_id: str, hours_ahead: int = 48) -> dict:
    """
    List upcoming calendar events that might need food orders.

    Args:
        user_id: The user's Firebase UID
        hours_ahead: How many hours ahead to look (default 48)

    Returns:
        List of upcoming events with attendee counts and locations
    """
    import asyncio
    from integrations.gcal.client import list_upcoming_events

    try:
        events = asyncio.get_event_loop().run_until_complete(
            list_upcoming_events(user_id, hours_ahead)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        events = loop.run_until_complete(list_upcoming_events(user_id, hours_ahead))
        loop.close()

    if not events:
        return {"events": [], "message": "No upcoming events found, or calendar not connected."}

    return {
        "events": [
            {
                "event_id": e.event_id,
                "title": e.title,
                "start_time": e.start_time.isoformat(),
                "end_time": e.end_time.isoformat(),
                "location": e.location,
                "attendee_count": len(e.attendee_emails),
            }
            for e in events
        ],
        "count": len(events),
    }


@tool
def create_lunch_calendar_event(
    user_id: str,
    vendor_name: str,
    delivery_time: str,
    headcount: int,
    attendee_emails: list[str],
) -> dict:
    """
    Create a lunch event on Google Calendar after order confirmation.

    Args:
        user_id: The user's Firebase UID
        vendor_name: Name of the restaurant/vendor
        delivery_time: ISO datetime string for when food arrives
        headcount: Number of people eating
        attendee_emails: List of attendee email addresses to invite

    Returns:
        Created event ID and confirmation
    """
    import asyncio
    from integrations.gcal.client import create_lunch_event

    try:
        event_id = asyncio.get_event_loop().run_until_complete(
            create_lunch_event(user_id, vendor_name, delivery_time, headcount, attendee_emails)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        event_id = loop.run_until_complete(
            create_lunch_event(user_id, vendor_name, delivery_time, headcount, attendee_emails)
        )
        loop.close()

    if not event_id:
        return {"error": "Failed to create calendar event. Calendar may not be connected."}

    return {
        "event_id": event_id,
        "message": f"Lunch event created for {vendor_name} with {headcount} attendees.",
    }


@tool
def get_attendee_dietary_info(user_id: str, event_id: str) -> dict:
    """
    Get aggregated dietary restrictions and allergies for all attendees of a calendar event.

    Args:
        user_id: The user's Firebase UID
        event_id: Google Calendar event ID

    Returns:
        Aggregated dietary restrictions, allergies, and per-attendee breakdown
    """
    import asyncio
    from integrations.gcal.client import get_event_details
    from integrations.gcal.attendee_resolver import resolve_attendees

    new_loop = False
    try:
        loop = asyncio.get_event_loop()
        event = loop.run_until_complete(get_event_details(user_id, event_id))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        new_loop = True
        event = loop.run_until_complete(get_event_details(user_id, event_id))

    if not event:
        if new_loop:
            loop.close()
        return {"error": "Event not found or calendar not connected."}

    try:
        report = loop.run_until_complete(resolve_attendees(event.attendee_emails))
    except RuntimeError:
        if new_loop:
            loop.close()
        loop = asyncio.new_event_loop()
        new_loop = True
        report = loop.run_until_complete(resolve_attendees(event.attendee_emails))

    if new_loop:
        loop.close()

    return {
        "event_title": event.title,
        "headcount": report.headcount,
        "dietary_restrictions": report.dietary_restrictions,
        "allergies": report.allergies,
        "unknown_attendees": len(report.unknown_attendees),
        "per_attendee": report.per_attendee,
        "summary": _build_dietary_summary(report),
    }


def _build_dietary_summary(report) -> str:
    """Build a human-readable dietary summary."""
    parts = [f"Headcount: {report.headcount}"]

    if report.dietary_restrictions:
        parts.append(f"Dietary: {', '.join(report.dietary_restrictions)}")
    if report.allergies:
        parts.append(f"ALLERGIES: {', '.join(report.allergies)}")
    if report.unknown_attendees:
        parts.append(f"{len(report.unknown_attendees)} attendees not in system (no dietary data)")

    return " | ".join(parts)


gcal_tools = [
    get_calendar_event,
    list_upcoming_meetings,
    create_lunch_calendar_event,
    get_attendee_dietary_info,
]
