"""The double-entry ledger: every entry debits one account and credits another."""

from dataclasses import dataclass
from decimal import Decimal

from .account import AccountStore, Account


@dataclass
class Entry:
    debit: str
    credit: str
    amount: Decimal
    memo: str = ""


class Ledger:
    def __init__(self, store: AccountStore):
        self.store = store
        self.entries: list[Entry] = []

    def append(self, debit: str, credit: str, amount: Decimal, memo: str = "") -> Entry:
        for account_id in (debit, credit):
            account = self.store.get(account_id)
            if account is None:
                raise KeyError(f"unknown account: {account_id}")
        if amount <= 0:
            raise ValueError("amount must be positive")
        entry = Entry(debit=debit, credit=credit, amount=amount, memo=memo)
        self.entries.append(entry)
        return entry

    def balance(self, account_id: str) -> Decimal:
        """Signed balance: positive for debit-normal accounts, negative for credit-normal."""
        account = self.store.get(account_id)
        if account is None:
            raise KeyError(f"unknown account: {account_id}")
        total = Decimal("0")
        for entry in self.entries:
            if entry.debit == account_id:
                total += entry.amount
            if entry.credit == account_id:
                total -= entry.amount
        return total if account.is_credit() is False else -total

    def totals(self) -> dict[str, Decimal]:
        return {a.id: self.balance(a.id) for a in self.store.all()}
