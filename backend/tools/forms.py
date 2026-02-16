"""Form tools for creating shareable dietary intake forms with Firestore storage."""

import os
import uuid
from collections import Counter
from datetime import datetime, timedelta
from langchain_core.tools import tool

from lib.firebase import create_form_doc, get_form_doc

# Base URL for shareable form links
FORM_BASE_URL = os.environ.get("POLL_BASE_URL", "https://your-modal-app.modal.run")

DIETARY_OPTIONS = [
    "Vegetarian", "Vegan", "Gluten-Free", "Halal",
    "Kosher", "Pescatarian", "Keto", "Dairy-Free",
]

ALLERGY_OPTIONS = [
    "Nuts", "Shellfish", "Dairy", "Eggs",
    "Soy", "Wheat", "Fish", "Sesame",
]


@tool
def create_dietary_form(
    title: str,
    team_name: str = "the team",
    deadline_hours: int = 48,
) -> dict:
    """Create a shareable dietary intake form for team members to submit their
    dietary restrictions, allergies, and food preferences. Use this when:
    - Planning food for an event and need to collect dietary info
    - User says "find out what everyone can eat" or "collect dietary info"
    - User wants to gather allergies/restrictions from the team
    - Ordering for a group and needs dietary data
    - "dietary survey", "what can everyone eat", "gather restrictions"

    Args:
        title: Form title (e.g. "Friday Lunch Dietary Needs")
        team_name: Name of the team/group (default "the team")
        deadline_hours: Hours until form closes (default 48)

    Returns:
        Form details with shareable link for team members to fill out
    """
    form_id = str(uuid.uuid4())
    deadline = datetime.utcnow() + timedelta(hours=deadline_hours)

    form_data = {
        "form_id": form_id,
        "type": "dietary_intake",
        "title": title,
        "team_name": team_name,
        "created_at": datetime.utcnow().isoformat(),
        "deadline": deadline.isoformat(),
        "is_closed": False,
        "responses": [],
        "total_responses": 0,
    }

    create_form_doc(form_id, form_data)

    share_url = f"{FORM_BASE_URL}/f/{form_id}"

    return {
        "form_id": form_id,
        "title": title,
        "share_url": share_url,
        "results_url": f"{share_url}/results",
        "deadline": deadline.isoformat(),
        "status": "created",
        "message": f"Dietary form created! Share this link with {team_name}: {share_url}",
    }


@tool
def get_form_responses(form_id: str) -> dict:
    """Get aggregated responses from a dietary intake form. Use this when:
    - User asks "how many people responded" or "what are the dietary needs"
    - Need to check form results before ordering food
    - "check the form", "dietary results", "form responses"

    Args:
        form_id: The form's unique identifier (from create_dietary_form result)

    Returns:
        Summary with response count, dietary breakdown, allergy breakdown, and notes
    """
    form = get_form_doc(form_id)
    if not form:
        return {"error": "Form not found"}

    responses = form.get("responses", [])
    total = len(responses)

    if total == 0:
        return {
            "form_id": form_id,
            "title": form.get("title", ""),
            "total_responses": 0,
            "message": "No responses yet. Share the form link with your team.",
            "share_url": f"{FORM_BASE_URL}/f/{form_id}",
        }

    # Aggregate dietary restrictions
    all_dietary = []
    for r in responses:
        all_dietary.extend(r.get("dietary_restrictions", []))
    dietary_counts = dict(Counter(all_dietary))

    # Aggregate allergies
    all_allergies = []
    for r in responses:
        all_allergies.extend(r.get("allergies", []))
    allergy_counts = dict(Counter(all_allergies))

    # Collect notes
    notes = [r["notes"] for r in responses if r.get("notes", "").strip()]

    # Respondent names
    respondents = [r.get("name", "Anonymous") for r in responses]

    return {
        "form_id": form_id,
        "title": form.get("title", ""),
        "total_responses": total,
        "dietary_summary": dietary_counts,
        "allergy_summary": allergy_counts,
        "notes": notes,
        "respondents": respondents,
        "is_closed": form.get("is_closed", False),
        "results_url": f"{FORM_BASE_URL}/f/{form_id}/results",
    }


form_tools = [create_dietary_form, get_form_responses]
