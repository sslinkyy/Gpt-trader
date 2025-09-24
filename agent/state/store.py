"""Simple in-memory state store for TradeStation-style data."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from agent.schemas.config import StateSchema


@dataclass
class AccountState:
    cash_free: float


class StateStore:
    """Provide query helpers for automation recipes."""

    def __init__(self, schema: StateSchema) -> None:
        self._accounts: Dict[str, AccountState] = {
            name: AccountState(cash_free=account.cash_free)
            for name, account in schema.accounts.items()
        }
        self._market = schema.market.copy()
        self._updated_at = datetime.utcnow()

    def account_cash_free(self, account: str) -> float:
        if account not in self._accounts:
            raise KeyError(f"Unknown account '{account}'")
        return self._accounts[account].cash_free

    def market_session(self) -> Optional[str]:
        return self._market.get("session")

    def snapshot(self) -> Dict[str, object]:
        return {
            "accounts": {name: vars(acc) for name, acc in self._accounts.items()},
            "market": self._market,
            "updated_at": self._updated_at.isoformat() + "Z",
        }


__all__ = ["StateStore"]
