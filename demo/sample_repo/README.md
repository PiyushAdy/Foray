# Ledgerline

A tiny double-entry ledger service used as the Foray demo repository.

Three processes share one SQLite store:

- `api/` - a stdlib HTTP server exposing the ledger over JSON
- `ingest/` - CSV import with currency normalization
- `worker/` - a Go reconciliation worker that checks balances

Run it:

```bash
python -m scripts.seed db.sqlite
python -m api.server
go run ./worker
```
