"""Account model and the SQLite-backed store."""

from dataclasses import dataclass, field
from pathlib import Path
import sqlite3


@dataclass
class Account:
    id: str
    name: str
    kind: str = "asset"
    meta: dict = field(default_factory=dict)

    def is_credit(self) -> bool:
        return self.kind in ("liability", "equity", "revenue")


SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id   TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL
);
"""


class AccountStore:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)

    def put(self, account: Account) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO accounts(id, name, kind) VALUES(?,?,?)",
            (account.id, account.name, account.kind),
        )
        self.conn.commit()

    def get(self, account_id: str) -> Account | None:
        row = self.conn.execute(
            "SELECT id, name, kind FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if row is None:
            return None
        return Account(id=row[0], name=row[1], kind=row[2])

    def all(self) -> list[Account]:
        rows = self.conn.execute("SELECT id, name, kind FROM accounts ORDER BY id").fetchall()
        return [Account(id=r[0], name=r[1], kind=r[2]) for r in rows]
