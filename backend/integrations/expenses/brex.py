"""Brex expense provider implementation."""

import os
import logging
import httpx

from integrations.expenses.base import ExpenseProvider, ExpenseResult
from models.integrations import ExpenseEntry

logger = logging.getLogger(__name__)

BREX_API_BASE = "https://platform.brexapis.com/v1"


class BrexProvider(ExpenseProvider):
    """Create expenses via the Brex API."""

    def __init__(self):
        self.api_key = os.environ.get("BREX_API_KEY", "")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_expense(self, expense: ExpenseEntry) -> ExpenseResult:
        """Create an expense entry in Brex.

        Maps to Brex's POST /expenses endpoint.
        """
        payload = {
            "amount": {
                "amount": int(expense.amount * 100),  # Brex uses cents
                "currency": expense.currency,
            },
            "merchant_name": expense.vendor_name,
            "memo": expense.description,
            "purchased_at": f"{expense.date}T12:00:00Z",
            "category": expense.category,
        }

        if expense.cost_center:
            payload["department_id"] = expense.cost_center

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{BREX_API_BASE}/expenses",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0,
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    return ExpenseResult(
                        expense_id=data.get("id", expense.expense_id),
                        status="submitted",
                        provider="brex",
                        message="Expense submitted to Brex.",
                    )
                else:
                    logger.error(f"Brex API error {response.status_code}: {response.text}")
                    return ExpenseResult(
                        expense_id=expense.expense_id,
                        status="failed",
                        provider="brex",
                        message=f"Brex API error: {response.status_code}",
                    )

        except Exception as e:
            logger.error(f"Brex expense creation failed: {e}")
            return ExpenseResult(
                expense_id=expense.expense_id,
                status="failed",
                provider="brex",
                message=str(e),
            )

    async def attach_receipt(self, expense_id: str, receipt_url: str, receipt_data: dict) -> bool:
        """Attach receipt to a Brex expense."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{BREX_API_BASE}/expenses/{expense_id}/receipt",
                    json={"receipt_uri": receipt_url},
                    headers=self.headers,
                    timeout=30.0,
                )
                return response.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Brex receipt attachment failed: {e}")
            return False
