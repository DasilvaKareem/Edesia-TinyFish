"""Ramp expense provider implementation."""

import os
import logging
import httpx

from integrations.expenses.base import ExpenseProvider, ExpenseResult
from models.integrations import ExpenseEntry

logger = logging.getLogger(__name__)

RAMP_API_BASE = "https://demo-api.ramp.com/developer/v1"


class RampProvider(ExpenseProvider):
    """Create expenses via the Ramp API."""

    def __init__(self):
        self.api_key = os.environ.get("RAMP_API_KEY", "")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_expense(self, expense: ExpenseEntry) -> ExpenseResult:
        """Create an expense entry in Ramp.

        Maps to Ramp's POST /reimbursements endpoint.
        """
        payload = {
            "amount": {
                "amount": int(expense.amount * 100),  # Ramp uses cents
                "currency_code": expense.currency,
            },
            "merchant": expense.vendor_name,
            "memo": expense.description,
            "transaction_date": expense.date,
            "receipts": [],
        }

        if expense.cost_center:
            payload["department"] = expense.cost_center

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{RAMP_API_BASE}/reimbursements",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0,
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    return ExpenseResult(
                        expense_id=data.get("id", expense.expense_id),
                        status="submitted",
                        provider="ramp",
                        message="Expense submitted to Ramp.",
                    )
                else:
                    logger.error(f"Ramp API error {response.status_code}: {response.text}")
                    return ExpenseResult(
                        expense_id=expense.expense_id,
                        status="failed",
                        provider="ramp",
                        message=f"Ramp API error: {response.status_code}",
                    )

        except Exception as e:
            logger.error(f"Ramp expense creation failed: {e}")
            return ExpenseResult(
                expense_id=expense.expense_id,
                status="failed",
                provider="ramp",
                message=str(e),
            )

    async def attach_receipt(self, expense_id: str, receipt_url: str, receipt_data: dict) -> bool:
        """Attach receipt to a Ramp expense."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{RAMP_API_BASE}/reimbursements/{expense_id}/receipt",
                    json={"receipt_url": receipt_url},
                    headers=self.headers,
                    timeout=30.0,
                )
                return response.status_code in (200, 201)
        except Exception as e:
            logger.error(f"Ramp receipt attachment failed: {e}")
            return False
