"""Stdlib HTTP server exposing the ledger over JSON."""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from core.account import AccountStore
from core.ledger import Ledger
from core import events
from .routes import route, resolve


def build_app(db_path: str) -> tuple[type, Ledger]:
    store = AccountStore(Path(db_path))
    ledger = Ledger(store)

    @route("GET", "/accounts")
    def accounts(_) -> bytes:
        return json.dumps([a.__dict__ for a in store.all()]).encode()

    @route("GET", "/totals")
    def totals(_) -> bytes:
        return json.dumps({k: str(v) for k, v in ledger.totals().items()}).encode()

    @route("POST", "/entries")
    def post_entry(body: bytes) -> bytes:
        payload = json.loads(body)
        entry = ledger.append(
            debit=payload["debit"],
            credit=payload["credit"],
            amount=__import__("decimal").Decimal(payload["amount"]),
            memo=payload.get("memo", ""),
        )
        events.entry_posted(entry.amount, entry.debit, entry.credit)
        return b'{"ok": true}'

    class Handler(BaseHTTPRequestHandler):
        def _dispatch(self, method: str) -> None:
            fn = resolve(method, self.path)
            if fn is None:
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            out = fn(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def do_GET(self) -> None:
            self._dispatch("GET")

        def do_POST(self) -> None:
            self._dispatch("POST")

        def log_message(self, fmt, *args) -> None:
            events.emit("http.request", path=self.path)

    return Handler, ledger


def serve(port: int = 7710, db_path: str = "ledger.db") -> None:
    handler, _ = build_app(db_path)
    server = HTTPServer(("127.0.0.1", port), handler)
    print(f"ledgerline listening on {port}")
    server.serve_forever()


if __name__ == "__main__":
    serve()
