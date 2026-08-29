"""CSV importer: turns bank rows into ledger entries."""

import csv
from decimal import Decimal
from pathlib import Path

from core.account import Account, AccountStore
from core.ledger import Ledger
from core import events
from .normalize import row_amount


def import_csv(path: Path, ledger: Ledger, store: AccountStore, default_credit: str = "equity:opening") -> int:
    """Import a CSV of rows into the ledger; returns the number of entries posted."""
    count = 0
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            amount = row_amount(row)
            debit = row.get("account", "assets:cash")
            credit = row.get("counter_account") or default_credit
            if store.get(debit) is None:
                store.put(Account(id=debit, name=debit, kind="asset"))
            ledger.append(debit=debit, credit=credit, amount=amount, memo=row.get("memo", ""))
            events.emit("ingest.row", account=debit, amount=amount)
            count += 1
    return count
