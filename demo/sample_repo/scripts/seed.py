"""Seed the ledger with a chart of accounts and opening balances."""

from decimal import Decimal
from pathlib import Path

from core.account import Account, AccountStore
from core.ledger import Ledger
from core import events


CHART = [
    Account(id="assets:cash", name="Cash", kind="asset"),
    Account(id="assets:bank", name="Bank", kind="asset"),
    Account(id="revenue:fees", name="Fees", kind="revenue"),
    Account(id="equity:opening", name="Opening balance", kind="equity"),
]


def seed(db_path: str = "ledger.db") -> Ledger:
    store = AccountStore(Path(db_path))
    for account in CHART:
        store.put(account)
    ledger = Ledger(store)
    ledger.append("assets:bank", "equity:opening", Decimal("1250.00"), "opening balance")
    ledger.append("assets:cash", "revenue:fees", Decimal("89.50"), "fees collected")
    events.emit("seed.complete", accounts=len(CHART))
    return ledger


if __name__ == "__main__":
    seed()
    print("seeded ledger.db")
