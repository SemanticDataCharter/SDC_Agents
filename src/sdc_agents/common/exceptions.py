"""Custom exceptions for SDC Agents."""

from __future__ import annotations


class InsufficientFundsError(Exception):
    """Raised when an SDCStudio API returns HTTP 402 (insufficient wallet balance)."""

    def __init__(
        self,
        message: str = "Insufficient credits.",
        *,
        estimated_cost: float | str = "",
        balance_remaining: float | str = "",
        estimated_cost_credits: int | str = "",
        balance_remaining_credits: int | str = "",
    ):
        self.estimated_cost = float(estimated_cost) if estimated_cost != "" else 0.0
        self.balance_remaining = float(balance_remaining) if balance_remaining != "" else 0.0

        # Credits are what the user is quoted. The server sends these; convert
        # from USD only when talking to an older server that does not.
        self.estimated_cost_credits = (
            int(estimated_cost_credits)
            if estimated_cost_credits != ""
            else int(round(self.estimated_cost * 1000))
        )
        self.balance_remaining_credits = (
            int(balance_remaining_credits)
            if balance_remaining_credits != ""
            else int(round(self.balance_remaining * 1000))
        )
        super().__init__(message)
