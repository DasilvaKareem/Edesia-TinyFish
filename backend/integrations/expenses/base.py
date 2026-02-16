"""Abstract expense provider interface."""

from abc import ABC, abstractmethod
from models.integrations import ExpenseEntry


class ExpenseResult:
    """Result from creating an expense."""

    def __init__(self, expense_id: str, status: str, provider: str, message: str = ""):
        self.expense_id = expense_id
        self.status = status
        self.provider = provider
        self.message = message

    def to_dict(self) -> dict:
        return {
            "expense_id": self.expense_id,
            "status": self.status,
            "provider": self.provider,
            "message": self.message,
        }


class ExpenseProvider(ABC):
    """Abstract interface for expense/accounting integrations."""

    @abstractmethod
    async def create_expense(self, expense: ExpenseEntry) -> ExpenseResult:
        """Create an expense entry in the external system.

        Args:
            expense: The expense data to submit.

        Returns:
            ExpenseResult with ID and status.
        """
        ...

    @abstractmethod
    async def attach_receipt(self, expense_id: str, receipt_url: str, receipt_data: dict) -> bool:
        """Attach a receipt to an existing expense.

        Args:
            expense_id: The expense ID from create_expense.
            receipt_url: URL to the receipt PDF in Firebase Storage.
            receipt_data: Structured receipt data dict.

        Returns:
            True if attached successfully.
        """
        ...
