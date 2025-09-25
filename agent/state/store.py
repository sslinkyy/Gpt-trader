"""Simple in-memory state store for TradeStation-style data."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from agent.schemas.config import StateSchema


@dataclass
class AccountState:
    cash_free: float


def _format_datetime(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    return normalized.isoformat().replace("+00:00", "Z")


@dataclass
class ActivityRecord:
    """Track what the agent is currently doing and has previously completed."""

    name: str
    status: str
    started_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "started_at": _format_datetime(self.started_at),
            "completed_at": _format_datetime(self.completed_at) if self.completed_at else None,
            "metadata": self.metadata,
            "error": self.error,
        }


class StateStore:
    """Provide query helpers for automation recipes."""

    def __init__(self, schema: StateSchema, *, history_limit: int = 50) -> None:
        self._accounts: Dict[str, AccountState] = {
            name: AccountState(cash_free=account.cash_free)
            for name, account in schema.accounts.items()
        }
        self._market = schema.market.copy()
        self._updated_at = datetime.now(timezone.utc)
        self._current_activity: Optional[ActivityRecord] = None
        self._activity_history: List[ActivityRecord] = []
        self._history_limit = max(0, history_limit)

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
            "activity": {
                "current": self._current_activity.to_dict() if self._current_activity else None,
                "history": [record.to_dict() for record in self._activity_history],
            },
            "updated_at": _format_datetime(self._updated_at),
        }

    @contextmanager
    def activity(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Iterator[None]:
        """Context manager for tracking ongoing automation work."""

        record = ActivityRecord(
            name=name,
            status="running",
            started_at=datetime.now(timezone.utc),
            metadata=dict(metadata or {}),
        )
        self._begin_activity(record)
        try:
            yield
        except Exception as exc:
            self._end_activity(record, status="failed", error=str(exc))
            raise
        else:
            self._end_activity(record, status="succeeded")

    def _begin_activity(self, record: ActivityRecord) -> None:
        self._current_activity = record
        self._updated_at = datetime.now(timezone.utc)

    def _end_activity(self, record: ActivityRecord, *, status: str, error: Optional[str] = None) -> None:
        if self._current_activity is not record:
            raise RuntimeError("Attempted to finish an activity that is not current.")
        record.status = status
        record.error = error
        record.completed_at = datetime.now(timezone.utc)
        self._activity_history.append(record)
        if self._history_limit and len(self._activity_history) > self._history_limit:
            self._activity_history = self._activity_history[-self._history_limit :]
        self._current_activity = None
        self._updated_at = datetime.now(timezone.utc)


__all__ = ["StateStore", "ActivityRecord"]
