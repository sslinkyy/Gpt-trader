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


def _serialize_windows(windows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    if not windows:
        return []
    sanitized: List[Dict[str, Any]] = []
    for window in windows:
        sanitized.append(dict(window))
    return sanitized


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
        self._process_registry: Dict[str, Dict[str, Any]] = {}

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
            "processes": {
                key: {k: v for k, v in value.items() if not k.startswith("_")}
                for key, value in self._process_registry.items()
            },
            "updated_at": _format_datetime(self._updated_at),
        }

    @contextmanager
    def activity(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> Iterator[None]:
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

    def register_process(
        self,
        *,
        app: str,
        instance_id: str,
        pid: int | None,
        preset: Optional[str],
        started_at: datetime,
        last_focused_at: Optional[datetime],
        status: str,
        windows: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        entry = self._process_registry.setdefault(instance_id, {})
        entry.update(
            {
                "instance_id": instance_id,
                "app": app,
                "pid": pid,
                "preset": preset,
                "status": status,
                "started_at": _format_datetime(started_at),
                "last_focused_at": _format_datetime(last_focused_at) if last_focused_at else None,
                "updated_at": _format_datetime(now),
                "windows": _serialize_windows(windows),
                "_updated_dt": now,
            }
        )
        self._updated_at = now

    def update_process(self, instance_id: str, **updates: Any) -> None:
        entry = self._process_registry.setdefault(
            instance_id, {"instance_id": instance_id, "status": "unknown"}
        )
        timestamp = updates.pop("timestamp", None)
        windows = updates.pop("windows", None)
        formatted_updates: Dict[str, Any] = {}
        for key, value in updates.items():
            if isinstance(value, datetime):
                formatted_updates[key] = _format_datetime(value)
            else:
                formatted_updates[key] = value
        entry.update(formatted_updates)
        if windows is not None:
            entry["windows"] = _serialize_windows(windows)
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        entry["updated_at"] = _format_datetime(timestamp)
        entry["_updated_dt"] = timestamp
        self._updated_at = datetime.now(timezone.utc)

    def remove_process(self, instance_id: str) -> None:
        if self._process_registry.pop(instance_id, None) is not None:
            self._updated_at = datetime.now(timezone.utc)

    def latest_instance_for(self, app: str) -> Optional[str]:
        latest_id: Optional[str] = None
        latest_dt: Optional[datetime] = None
        for entry in self._process_registry.values():
            if entry.get("app") != app:
                continue
            if entry.get("status") in {"closed", "killed"}:
                continue
            updated = entry.get("_updated_dt")
            if not isinstance(updated, datetime):
                continue
            if latest_dt is None or updated > latest_dt:
                latest_dt = updated
                latest_id = entry["instance_id"]
        return latest_id

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
