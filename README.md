# OpenGTM Engine

A clean-room, local-only, open-source outbound drafting tool under NativeLayer.
MIT licensed. Inspired by the *public interface* of PumpGTM's MIT-licensed
reference repos (`pumpgtm-mcp` tools list, `pumpgtm-api` OpenAPI spec) — **not**
a copy of PumpGTM. No PumpGTM code, assets, branding, logo, or name is used.
No PumpGTM service is called.

## What it is

- Lead intake: CSV import + manual add (CLI and REST API), deduped by email, else LinkedIn URL.
- Deterministic, explainable intent scoring 0–100 from signals *you* supply:
  hiring +25, funding +25, post engagement +20, competitor customer +15,
  founder / C-level / VP / Director / Head role fit +15, capped at 100.
- A 4-step sequence engine that generates **drafts only**:
  1. LinkedIn connection request draft
  2. LinkedIn follow-up draft
  3. Email draft
  4. X draft
- A hard human-approval gate: a step stays `draft` until a named human
  approves it, and can only be marked `sent` after approval — and only by
  the human, after they send it themselves outside this tool.
- Daily caps enforced at mark-sent time (defaults: LinkedIn 30/day,
  email 50/day, X 20/day, configurable in `config.json`).
- A Markdown CRM (`crm/OPENCRM.md`) generated from SQLite — readable with
  no database.
- A manual reply inbox: you read replies yourself and log them.
- REST API (FastAPI, OpenAPI) + MCP server over stdio + CLI.

## What it is NOT

- **It does not send anything.** No LinkedIn, email, or X sending, no
  automation, no scraping, no browser driving, no session cookies.
- **It has no buyer database and no enrichment.** There is no 2B-contact
  list here. Scores come only from signals you enter. Do not treat a
  score as proof someone wants to buy.
- **It is not PumpGTM.** It does not connect to PumpGTM, copy its code,
  or reproduce its hosted service.
- No auth, no OAuth, no deployment, no GitHub repo yet. Local only.

## ⚠️ Terms-of-service warning

Automated LinkedIn outreach violates LinkedIn's terms and can get an
account restricted or banned. Automated scraping and bulk unsolicited
email carry the same risk on their platforms, plus spam-law risk.
This tool is deliberately draft-only with a human gate and daily caps
to keep a human in control. You are responsible for how you use the
drafts, for complying with LinkedIn / X / email-provider terms, and for
only contacting people you have a lawful basis to contact. When in
doubt, send manually, slowly, and only to people who plausibly want
to hear from you.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.11+; deps are FastAPI + Uvicorn + httpx + pytest only.
Storage is stdlib `sqlite3` (`leads.db`, created on first use).

## Run

```bash
# Server (local only, port 8040)
python cli.py serve
# or: uvicorn app:app --host 127.0.0.1 --port 8040

# CLI
python cli.py import-csv sample_leads.csv
python cli.py list-leads
python cli.py add-lead --name "Ada Example" --company "Example Analytics" \
  --role Founder --email ada@example.test --signals hiring,funding
python cli.py score 1
python cli.py create-sequence 1
python cli.py approve 1 --step 1 --approver Rashad
# ... send step 1 yourself in LinkedIn, then:
python cli.py mark-sent 1 --step 1 --by Rashad
python cli.py log-reply 1 --channel linkedin --outcome replied --text "Interested, book a call"
python cli.py export-crm
python cli.py stats
```

## Config

`config.json` — daily caps and port:

```json
{"daily_caps": {"linkedin": 30, "email": 50, "x": 20}, "port": 8040}
```

Override paths with env vars: `OPENGTM_DB_PATH`, `OPENGTM_CONFIG_PATH`.

## REST API (port 8040)

OpenAPI docs at `http://127.0.0.1:8040/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| GET/POST | `/api/leads` | List / add a lead |
| GET | `/api/leads/{id}` | One lead |
| POST | `/api/leads/import` | CSV upload import |
| POST | `/api/leads/{id}/score` | Re-score a lead |
| GET/POST | `/api/sequences` | List / create a sequence |
| GET | `/api/sequences/{id}` | One sequence + steps |
| POST | `/api/sequences/{id}/approve-step` | Approve a draft step |
| POST | `/api/sequences/{id}/mark-sent` | Mark an approved step sent (cap-checked) |
| GET/POST | `/api/replies` | List / log a reply |
| GET | `/api/stats` | Counts, caps, today's sent |
| GET/POST | `/api/crm/export` | Generate / fetch `crm/OPENCRM.md` |

`mark-sent` on an unapproved step returns 400. Over the daily cap returns 400.

## MCP server

```bash
python mcp_server.py   # stdio JSON-RPC 2.0
```

Methods: `initialize`, `ping`, `tools/list`, `tools/call`.

Tools (own names, generic concepts): `list_leads`, `get_lead`,
`score_lead`, `create_sequence`, `get_sequence`, `approve_step`,
`list_replies`, `log_reply`, `get_stats`. Note: there is deliberately
no `mark_sent` MCP tool — marking sent is a CLI/API action tied to a
human who just sent the message themselves.

## Sample data

`sample_leads.csv` has 5 **fictional** leads only (Example Analytics,
Sample Roofing Co, Testbridge Labs, DemoWorks, Placeholder Studio).
No real people.

## Tests

```bash
python -m pytest tests/ -q
```

## Limits (honest)

- No live LinkedIn / email / X sending, no OAuth, no inbox reading.
- No buyer database, no enrichment, no intent data beyond what you enter.
- No auth — local only, do not expose port 8040 publicly.
- No deployment, no GitHub repo created by this build.

## License

MIT — Copyright (c) 2026 Rashad Durrand Smith / NativeLayer. See `LICENSE`.
