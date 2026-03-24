"""Custom exceptions for SDC Agents."""

from __future__ import annotations


class InsufficientFundsError(Exception):
    """Raised when an SDCStudio API returns HTTP 402 (insufficient wallet balance)."""

    def __init__(
        self,
        message: str = "Insufficient wallet balance.",
        *,
        estimated_cost: float | str = "",
        balance_remaining: float | str = "",
    ):
        self.estimated_cost = float(estimated_cost) if estimated_cost != "" else 0.0
        self.balance_remaining = float(balance_remaining) if balance_remaining != "" else 0.0
        super().__init__(message)
