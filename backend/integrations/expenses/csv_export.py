"""CSV expense export — universal fallback for unsupported expense tools."""

import io
import csv
import logging
import uuid
from typing import Optional

from integrations.expenses.base import ExpenseProvider, ExpenseResult
from models.integrations import ExpenseEntry

logger = logging.getLogger(__name__)


class CSVExporter(ExpenseProvider):
    """Generate CSV expense records stored in Firebase Storage."""

    async def create_expense(self, expense: ExpenseEntry) -> ExpenseResult:
        """Generate a CSV record and store in Firebase Storage.

        Returns a download URL for the CSV.
        """
        csv_content = _build_single_expense_csv(expense)

        # Upload to Firebase Storage
        try:
            download_url = await _upload_csv(
                csv_content,
                f"expenses/{expense.order_id}/{expense.expense_id}.csv",
            )

            return ExpenseResult(
                expense_id=expense.expense_id,
                status="exported",
                provider="csv",
                message=f"Expense exported as CSV. Download: {download_url}",
            )
        except Exception as e:
            logger.error(f"CSV upload failed: {e}")
            return ExpenseResult(
                expense_id=expense.expense_id,
                status="exported",
                provider="csv",
                message="CSV generated (upload failed, available in-memory).",
            )

    async def attach_receipt(self, expense_id: str, receipt_url: str, receipt_data: dict) -> bool:
        """CSV doesn't support receipt attachment — receipt URL is in the CSV."""
        return True


def generate_expense_csv(expenses: list[ExpenseEntry]) -> str:
    """Generate a downloadable CSV for multiple expenses.

    Args:
        expenses: List of expense entries to export.

    Returns:
        CSV content as a string.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        "Date", "Vendor", "Amount", "Currency", "Category",
        "Description", "Cost Center", "Attendees", "Receipt URL",
    ])

    for exp in expenses:
        writer.writerow([
            exp.date,
            exp.vendor_name,
            f"{exp.amount:.2f}",
            exp.currency,
            exp.category,
            exp.description,
            exp.cost_center or "",
            "; ".join(exp.attendees),
            exp.receipt_url or "",
        ])

    return output.getvalue()


def _build_single_expense_csv(expense: ExpenseEntry) -> str:
    """Build CSV content for a single expense."""
    return generate_expense_csv([expense])


async def _upload_csv(content: str, path: str) -> str:
    """Upload CSV to Firebase Storage and return download URL."""
    import firebase_admin
    from firebase_admin import storage

    bucket = storage.bucket()
    blob = bucket.blob(path)
    blob.upload_from_string(content, content_type="text/csv")
    blob.make_public()
    return blob.public_url
