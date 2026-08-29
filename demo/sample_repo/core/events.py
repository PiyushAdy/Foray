"""Domain events emitted when the ledger changes."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable


@dataclass
class Event:
    kind: str
    payload: dict = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


Listener = Callable[[Event], None]
_listeners: list[Listener] = []


def subscribe(listener: Listener) -> Callable[[], None]:
    _listeners.append(listener)

    def off() -> None:
        _listeners.remove(listener)

    return off


def emit(kind: str, **payload) -> Event:
    event = Event(kind=kind, payload=payload)
    for listener in _listeners:
        listener(event)
    return event


def entry_posted(amount: Decimal, debit: str, credit: str) -> Event:
    return emit("entry.posted", amount=amount, debit=debit, credit=credit)
