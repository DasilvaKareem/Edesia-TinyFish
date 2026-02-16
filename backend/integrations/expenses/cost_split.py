"""Cost center splitting for orders across teams."""

import uuid
from models.integrations import ExpenseEntry, CostSplit


def calculate_split(
    total: float,
    order_id: str,
    vendor_name: str,
    date: str,
    description: str,
    splits: list[dict],
    attendees: list[str] = None,
    provider: str = "csv",
) -> list[ExpenseEntry]:
    """Split a single order into multiple expense entries by cost center.

    Args:
        total: Total order amount.
        order_id: Original order ID.
        vendor_name: Vendor name.
        date: Order date (YYYY-MM-DD).
        description: Base expense description.
        splits: List of dicts with "team" and "pct" (percentage) keys.
            e.g. [{"team": "Engineering", "pct": 60}, {"team": "Design", "pct": 40}]
        attendees: Optional list of attendee names/emails.
        provider: Expense provider to use.

    Returns:
        List of ExpenseEntry objects, one per cost center.
    """
    entries = []

    # Validate splits add up to ~100%
    total_pct = sum(s.get("pct", 0) for s in splits)
    if abs(total_pct - 100) > 1:
        # Normalize to 100%
        for s in splits:
            s["pct"] = (s["pct"] / total_pct) * 100

    remaining = total
    for i, split in enumerate(splits):
        pct = split.get("pct", 0)
        team = split.get("team", f"Team {i + 1}")

        if i == len(splits) - 1:
            # Last split gets the remainder to avoid rounding issues
            amount = round(remaining, 2)
        else:
            amount = round(total * (pct / 100), 2)
            remaining -= amount

        entries.append(ExpenseEntry(
            expense_id=str(uuid.uuid4()),
            order_id=order_id,
            vendor_name=vendor_name,
            amount=amount,
            category="Meals & Entertainment",
            description=f"{description} ({team} — {pct:.0f}%)",
            date=date,
            attendees=attendees or [],
            cost_center=team,
            provider=provider,
        ))

    return entries
