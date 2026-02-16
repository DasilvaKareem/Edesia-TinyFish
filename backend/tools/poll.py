"""Poll tool for creating and managing office polls with Firestore storage."""

import os
import uuid
from datetime import datetime, timedelta
from typing import Optional
from langchain_core.tools import tool

from lib.firebase import create_poll_doc, get_poll_doc, update_poll_doc

# Base URL for shareable poll links (set via environment or default to Modal URL)
POLL_BASE_URL = os.environ.get("POLL_BASE_URL", "https://your-modal-app.modal.run")


@tool
def create_poll(
    question: str,
    options: list[str],
    deadline_hours: int = 24,
) -> dict:
    """Create a shareable poll for team voting. Use this when the user wants to:
    - Let their team vote on lunch/dinner options
    - Survey the office for food preferences
    - Decide between restaurants, cuisines, or vendors
    - Run any kind of group vote or preference check
    - "let the team decide", "ask the team", "send options to the team"

    Args:
        question: The poll question (e.g. "Where should we order lunch?")
        options: List of 2-10 voting options (e.g. ["Chipotle", "Panera", "Subway"])
        deadline_hours: Hours until poll closes (default 24)

    Returns:
        Poll with shareable voting link and results link
    """
    if len(options) < 2:
        return {"error": "Poll must have at least 2 options"}
    if len(options) > 10:
        return {"error": "Poll cannot have more than 10 options"}

    poll_id = str(uuid.uuid4())
    deadline = datetime.utcnow() + timedelta(hours=deadline_hours)

    poll = {
        "poll_id": poll_id,
        "question": question,
        "options": [
            {"option_id": str(uuid.uuid4()), "text": opt, "votes": 0}
            for opt in options
        ],
        "deadline": deadline.isoformat(),
        "created_at": datetime.utcnow().isoformat(),
        "votes": [],
        "is_closed": False,
        "total_votes": 0,
    }

    # Store in Firestore
    create_poll_doc(poll_id, poll)

    # Generate shareable link
    share_url = f"{POLL_BASE_URL}/p/{poll_id}"

    return {
        "poll_id": poll_id,
        "question": question,
        "options": [o["text"] for o in poll["options"]],
        "deadline": deadline.isoformat(),
        "share_url": share_url,
        "results_url": f"{share_url}/results",
        "status": "created",
        "message": f"Poll created! Share this link with your team: {share_url}",
    }


@tool
def send_poll_webhook(poll_id: str, webhook_url: str) -> dict:
    """Send a poll to a webhook URL (e.g. Slack channel). Requires user approval before sending.
    Use this after create_poll when the user wants to distribute the poll via webhook.

    Args:
        poll_id: The poll's unique identifier (from create_poll result)
        webhook_url: URL to POST the poll data to (e.g. Slack webhook URL)

    Returns:
        Pending action requiring approval before sending
    """
    poll = get_poll_doc(poll_id)
    if not poll:
        return {"error": "Poll not found"}

    # Create pending action for approval
    action = {
        "action_id": str(uuid.uuid4()),
        "action_type": "poll_send",
        "status": "pending_approval",
        "description": f"Send poll '{poll['question'][:50]}...' to webhook",
        "payload": {
            "poll_id": poll_id,
            "webhook_url": webhook_url,
            "poll_data": {
                "poll_id": poll["poll_id"],
                "question": poll["question"],
                "options": poll["options"],
                "deadline": poll["deadline"],
                "vote_endpoint": f"/polls/{poll_id}/vote",
            },
        },
    }

    return action


@tool
def get_poll_results(poll_id: str) -> dict:
    """Get current vote counts and results for a poll. Use this when the user asks:
    - "how's the poll going", "what are the results", "who's winning"
    - "check the votes", "poll status"

    Args:
        poll_id: The poll's unique identifier (from create_poll result)

    Returns:
        Vote counts per option, percentages, winner, and tie detection
    """
    poll = get_poll_doc(poll_id)
    if not poll:
        return {"error": "Poll not found"}

    total_votes = sum(opt["votes"] for opt in poll["options"])

    results = {
        "poll_id": poll_id,
        "question": poll["question"],
        "total_votes": total_votes,
        "is_closed": poll["is_closed"],
        "deadline": poll["deadline"],
        "results": [
            {
                "option": opt["text"],
                "votes": opt["votes"],
                "percentage": round(opt["votes"] / total_votes * 100, 1) if total_votes > 0 else 0,
            }
            for opt in sorted(poll["options"], key=lambda x: x["votes"], reverse=True)
        ],
    }

    # Determine winner
    if total_votes > 0:
        top_vote = max(opt["votes"] for opt in poll["options"])
        winners = [opt["text"] for opt in poll["options"] if opt["votes"] == top_vote]
        results["winner"] = winners[0] if len(winners) == 1 else None
        results["is_tie"] = len(winners) > 1
        if results["is_tie"]:
            results["tied_options"] = winners

    return results


@tool
def analyze_poll_results(poll_id: str) -> dict:
    """Get detailed statistical analysis of poll results with recommendations.
    Use this when the user wants deeper insights beyond basic vote counts:
    - "analyze the poll", "give me insights", "what should we pick"
    - Provides participation rate, vote spread, winner margin, and action recommendation

    Args:
        poll_id: The poll's unique identifier (from create_poll result)

    Returns:
        Statistics, participation insights, winner analysis, and recommendation
    """
    poll = get_poll_doc(poll_id)
    if not poll:
        return {"error": "Poll not found"}

    total_votes = sum(opt["votes"] for opt in poll["options"])

    if total_votes == 0:
        return {
            "poll_id": poll_id,
            "analysis": "No votes have been cast yet.",
            "recommendation": "Wait for more responses before making a decision.",
        }

    # Calculate statistics
    votes = [opt["votes"] for opt in poll["options"]]
    avg_votes = sum(votes) / len(votes)
    max_votes = max(votes)
    min_votes = min(votes)

    # Find winner(s)
    winners = [opt for opt in poll["options"] if opt["votes"] == max_votes]

    # Participation rate insight
    participation_insight = ""
    if total_votes < 5:
        participation_insight = "Low participation - consider sending reminders."
    elif total_votes < 10:
        participation_insight = "Moderate participation."
    else:
        participation_insight = "Good participation rate!"

    # Winner insight
    if len(winners) == 1:
        winner = winners[0]
        margin = winner["votes"] - (sorted(votes, reverse=True)[1] if len(votes) > 1 else 0)
        winner_pct = round(winner["votes"] / total_votes * 100, 1)
        winner_insight = f"Clear winner: '{winner['text']}' with {winner_pct}% of votes (margin of {margin} votes)."
    else:
        winner_insight = f"Tie between: {', '.join(w['text'] for w in winners)}. Consider a runoff poll."

    return {
        "poll_id": poll_id,
        "question": poll["question"],
        "total_votes": total_votes,
        "statistics": {
            "average_votes_per_option": round(avg_votes, 2),
            "highest_votes": max_votes,
            "lowest_votes": min_votes,
            "vote_spread": max_votes - min_votes,
        },
        "insights": {
            "participation": participation_insight,
            "winner": winner_insight,
        },
        "recommendation": (
            f"Proceed with '{winners[0]['text']}'" if len(winners) == 1
            else "Run a tiebreaker between the top options"
        ),
    }


poll_tools = [create_poll, send_poll_webhook, get_poll_results, analyze_poll_results]
