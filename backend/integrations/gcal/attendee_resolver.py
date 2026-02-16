"""Cross-reference calendar attendees with stored food preferences."""

import logging
from typing import Optional

from models.integrations import AttendeeReport

logger = logging.getLogger(__name__)


async def resolve_attendees(attendee_emails: list[str]) -> AttendeeReport:
    """Resolve calendar attendees to Edesia users and aggregate dietary info.

    For each attendee email:
    1. Look up Firebase user by email
    2. Load their food preferences from Firestore
    3. Aggregate dietary restrictions and allergies across all attendees

    Args:
        attendee_emails: List of email addresses from a calendar event.

    Returns:
        AttendeeReport with aggregated dietary data.
    """
    from lib.firebase import get_db

    db = get_db()

    all_restrictions = set()
    all_allergies = set()
    per_attendee = {}
    unknown = []

    for email in attendee_emails:
        # Look up user by email
        users = db.collection("users").where("email", "==", email).limit(1).stream()

        user_data = None
        for doc in users:
            user_data = doc.to_dict()
            break

        if not user_data:
            unknown.append(email)
            per_attendee[email] = {"name": email.split("@")[0], "restrictions": [], "allergies": []}
            continue

        # Extract preferences
        name = user_data.get("displayName") or user_data.get("companyName") or email.split("@")[0]
        restrictions = user_data.get("dietaryRestrictions", []) or []
        allergies = user_data.get("allergies", []) or []

        all_restrictions.update(restrictions)
        all_allergies.update(allergies)

        per_attendee[email] = {
            "name": name,
            "restrictions": restrictions,
            "allergies": allergies,
        }

    return AttendeeReport(
        headcount=len(attendee_emails),
        dietary_restrictions=sorted(all_restrictions),
        allergies=sorted(all_allergies),
        per_attendee=per_attendee,
        unknown_attendees=unknown,
    )
