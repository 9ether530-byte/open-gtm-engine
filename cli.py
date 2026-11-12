"""OpenGTM Engine CLI.

Usage examples:
  python cli.py import-csv sample_leads.csv
  python cli.py add-lead --name "Ada Example" --company "Example Co" --role "Founder" --email ada@example.test --signals hiring,funding
  python cli.py list-leads
  python cli.py score 1
  python cli.py create-sequence 1
  python cli.py approve 1 --step 1 --approver Rashad
  python cli.py mark-sent 1 --step 1 --by Rashad
  python cli.py log-reply 1 --channel linkedin --outcome replied --text "Interested, book a call"
  python cli.py export-crm
  python cli.py stats
  python cli.py serve
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import engine
from config import load_config


def _print(obj):
    print(json.dumps(obj, indent=2, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="opengtm", description="OpenGTM Engine CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import-csv", help="Import leads from a CSV file")
    p.add_argument("path")

    p = sub.add_parser("add-lead", help="Add one lead manually")
    p.add_argument("--name", required=True)
    p.add_argument("--company", default="")
    p.add_argument("--role", default="")
    p.add_argument("--email", default="")
    p.add_argument("--linkedin-url", default="")
    p.add_argument("--x-handle", default="")
    p.add_argument("--source", default="")
    p.add_argument("--signals", default="")
    p.add_argument("--notes", default="")

    p = sub.add_parser("list-leads", help="List leads, highest score first")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--min-score", type=int, default=None)

    p = sub.add_parser("score", help="Re-score a lead")
    p.add_argument("lead_id", type=int)

    p = sub.add_parser("create-sequence", help="Create a 4-step draft sequence for a lead")
    p.add_argument("lead_id", type=int)
    p.add_argument("--name", default="")

    p = sub.add_parser("approve", help="Human-approve one sequence step (draft -> approved)")
    p.add_argument("sequence_id", type=int)
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--approver", required=True)

    p = sub.add_parser("mark-sent", help="Mark an approved step sent (human sent it themselves)")
    p.add_argument("sequence_id", type=int)
    p.add_argument("--step", type=int, required=True)
    p.add_argument("--by", required=True)

    p = sub.add_parser("log-reply", help="Log a reply manually")
    p.add_argument("lead_id", type=int)
    p.add_argument("--channel", required=True, choices=["linkedin", "email", "x"])
    p.add_argument("--outcome", required=True,
                   choices=["replied", "meeting_booked", "not_interested", "no_reply"])
    p.add_argument("--text", default="")

    sub.add_parser("export-crm", help="Write crm/OPENCRM.md from SQLite")
    sub.add_parser("stats", help="Show counts, caps, and today's sent totals")
    sub.add_parser("serve", help="Run the FastAPI server on port 8040")

    args = parser.parse_args(argv)

    try:
        if args.cmd == "import-csv":
            _print(engine.import_csv(csv_path=args.path))
        elif args.cmd == "add-lead":
            _print(engine.add_lead(
                name=args.name, company=args.company, role=args.role,
                email=args.email, linkedin_url=args.linkedin_url,
                x_handle=args.x_handle, source=args.source,
                signals=args.signals, notes=args.notes,
            ))
        elif args.cmd == "list-leads":
            _print(engine.list_leads(limit=args.limit, min_score=args.min_score))
        elif args.cmd == "score":
            _print(engine.score_lead(lead_id=args.lead_id))
        elif args.cmd == "create-sequence":
            _print(engine.create_sequence(lead_id=args.lead_id, name=args.name))
        elif args.cmd == "approve":
            _print(engine.approve_step(
                sequence_id=args.sequence_id, step_number=args.step, approver=args.approver))
        elif args.cmd == "mark-sent":
            _print(engine.mark_sent(
                sequence_id=args.sequence_id, step_number=args.step, marked_by=args.by))
        elif args.cmd == "log-reply":
            _print(engine.log_reply(
                lead_id=args.lead_id, channel=args.channel,
                text=args.text, outcome=args.outcome))
        elif args.cmd == "export-crm":
            path = engine.export_crm()
            print(f"Wrote {path}")
        elif args.cmd == "stats":
            _print(engine.get_stats())
        elif args.cmd == "serve":
            import uvicorn

            port = load_config()["port"]
            print(f"OpenGTM Engine on http://127.0.0.1:{port} (local only, drafts only)")
            uvicorn.run("app:app", host="127.0.0.1", port=port)
    except (ValueError, LookupError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
