"""Expense LangGraph tools for the Edesia agent."""

from typing import Optional
from langchain_core.tools import tool


@tool
def generate_expense(order_id: str, cost_splits: Optional[list[dict]] = None) -> dict:
    """
    Generate an expense entry for a completed order.

    Automatically selects the user's configured expense provider (Ramp, Brex, or CSV).
    Optionally splits across cost centers.

    Args:
        order_id: The completed order ID
        cost_splits: Optional list of cost center splits, e.g. [{"team": "Engineering", "pct": 60}, {"team": "Design", "pct": 40}]

    Returns:
        Expense entry details with provider, status, and download URL (for CSV)
    """
    import asyncio
    from lib.firebase import get_db
    from integrations.expenses.receipt import build_receipt, render_receipt_text

    db = get_db()

    # Find the order in Firestore
    orders = db.collection_group("orders").where("orderId", "==", order_id).limit(1).stream()

    order_data = None
    for doc in orders:
        order_data = doc.to_dict()
        break

    if not order_data:
        return {"error": f"Order {order_id} not found."}

    # Determine provider from user settings
    user_id = order_data.get("userId", "")
    user_doc = db.collection("users").document(user_id).get() if user_id else None
    user_data = user_doc.to_dict() if user_doc and user_doc.exists else {}
    provider_name = user_data.get("expenseProvider", "csv")

    # Build expense entry
    from models.integrations import ExpenseEntry
    from datetime import datetime

    total = order_data.get("estimatedCost") or order_data.get("actualCost") or 0
    vendor = order_data.get("vendor", "Unknown")
    date = order_data.get("eventDate", datetime.utcnow().strftime("%Y-%m-%d"))
    headcount = order_data.get("guestCount", 0)

    if cost_splits:
        from integrations.expenses.cost_split import calculate_split
        entries = calculate_split(
            total=total,
            order_id=order_id,
            vendor_name=vendor,
            date=date,
            description=f"Lunch order from {vendor} ({headcount} people)",
            splits=cost_splits,
            provider=provider_name,
        )
    else:
        entries = [ExpenseEntry(
            order_id=order_id,
            vendor_name=vendor,
            amount=total,
            description=f"Lunch order from {vendor} ({headcount} people)",
            date=date,
            cost_center=user_data.get("defaultCostCenter"),
            provider=provider_name,
        )]

    # Submit to provider
    provider = _get_provider(provider_name)

    results = []
    for entry in entries:
        try:
            result = asyncio.get_event_loop().run_until_complete(
                provider.create_expense(entry)
            )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(provider.create_expense(entry))
            loop.close()

        results.append(result.to_dict())

    return {
        "expenses": results,
        "provider": provider_name,
        "total": total,
        "splits": len(entries) if cost_splits else 0,
        "message": f"{'Expenses' if len(entries) > 1 else 'Expense'} submitted via {provider_name}.",
    }


@tool
def export_expenses_csv(start_date: str, end_date: str) -> dict:
    """
    Export expenses as a downloadable CSV for a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Download URL for the CSV file
    """
    from lib.firebase import get_db
    from integrations.expenses.csv_export import generate_expense_csv
    from models.integrations import ExpenseEntry

    db = get_db()

    # Query expenses in date range
    expenses_ref = db.collection("expenses") \
        .where("date", ">=", start_date) \
        .where("date", "<=", end_date) \
        .stream()

    entries = []
    for doc in expenses_ref:
        data = doc.to_dict()
        entries.append(ExpenseEntry(
            expense_id=doc.id,
            order_id=data.get("orderId", ""),
            vendor_name=data.get("vendorName", ""),
            amount=data.get("amount", 0),
            category=data.get("category", "Meals & Entertainment"),
            description=data.get("description", ""),
            date=data.get("date", ""),
            attendees=data.get("attendees", []),
            cost_center=data.get("costCenter"),
            receipt_url=data.get("receiptUrl"),
            provider=data.get("provider", "csv"),
            status=data.get("status", "submitted"),
        ))

    if not entries:
        return {"error": f"No expenses found between {start_date} and {end_date}."}

    csv_content = generate_expense_csv(entries)

    # Upload CSV
    import asyncio
    from integrations.expenses.csv_export import _upload_csv

    try:
        url = asyncio.get_event_loop().run_until_complete(
            _upload_csv(csv_content, f"exports/expenses_{start_date}_{end_date}.csv")
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        url = loop.run_until_complete(
            _upload_csv(csv_content, f"exports/expenses_{start_date}_{end_date}.csv")
        )
        loop.close()

    total = sum(e.amount for e in entries)

    return {
        "download_url": url,
        "count": len(entries),
        "total": total,
        "date_range": f"{start_date} to {end_date}",
        "message": f"Exported {len(entries)} expenses (${total:.2f} total).",
    }


def _get_provider(name: str):
    """Get the expense provider instance by name."""
    if name == "ramp":
        from integrations.expenses.ramp import RampProvider
        return RampProvider()
    elif name == "brex":
        from integrations.expenses.brex import BrexProvider
        return BrexProvider()
    else:
        from integrations.expenses.csv_export import CSVExporter
        return CSVExporter()


expense_tools = [generate_expense, export_expenses_csv]
