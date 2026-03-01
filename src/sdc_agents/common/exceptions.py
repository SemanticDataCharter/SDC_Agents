"""Custom exceptions for SDC Agents."""

from __future__ import annotations


class InsufficientFundsError(Exception):
    """Raised when an SDCStudio API returns HTTP 402 (insufficient wallet balance)."""

    def __init__(
        self,
        message: str = "Insufficient wallet balance.",
        *,
        estimated_cost: str = "",
        balance_remaining: str = "",
    ):
        self.estimated_cost = estimated_cost
        self.balance_remaining = balance_remaining
        super().__init__(message)
