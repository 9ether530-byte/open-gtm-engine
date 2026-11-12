"""OpenGTM Engine — core logic. Local only, stdlib sqlite3.

Clean-room implementation. No LinkedIn/email/X sending, no scraping,
no external enrichment, no buyer database. Sequences are DRAFTS only;
a human must approve a step, then manually send it outside this tool
and mark it sent. Daily caps are enforced at mark-sent time.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from config import get_caps

ALLOWED_SIGNALS = {"hiring", "funding", "post_engagement", "competitor_customer"}
SIGNAL_POINTS = {
    "hiring": 25,
    "funding": 25,
    "post_engagement": 20,
    "competitor_customer": 15,
}
ROLE_FIT_POINTS = 15
ROLE_FIT_TOKENS = (
    "founder", "ceo", "cto", "cfo", "coo", "chief", "vp", "vice president",
    "director", "head",
)
ALLOWED_CHANNELS = {"linkedin", "email", "x"}
ALLOWED_OUTCOMES = {"replied", "meeting_booked", "not_interested", "no_reply"}
ALLOWED_STEP_STATUSES = {"draft", "approved", "sent"}

BASE_DIR = Path(__file__).parent


def db_path(db: str | Path | None = None) -> Path:
    if db:
        return Path(db)
    env = os.environ.get("OPENGTM_DB_PATH")
    return Path(env) if env else BASE_DIR / "leads.db"


def _connect(db: str | Path | None = None) -> sqlite3.Connection:
    p = db_path(db)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db: str | Path | None = None) -> Path:
    p = db_path(db)
    with _connect(p) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                linkedin_url TEXT NOT NULL DEFAULT '',
                x_handle TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                signals TEXT NOT NULL DEFAULT '[]',
                notes TEXT NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0,
                score_reasons TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sequences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id),
                name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sequence_id INTEGER NOT NULL REFERENCES sequences(id),
                step_number INTEGER NOT NULL,
                channel TEXT NOT NULL,
                kind TEXT NOT NULL,
                draft_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                approved_by TEXT NOT NULL DEFAULT '',
                approved_at TEXT NOT NULL DEFAULT '',
                marked_sent_by TEXT NOT NULL DEFAULT '',
                sent_at TEXT NOT NULL DEFAULT '',
                UNIQUE(sequence_id, step_number)
            );
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL REFERENCES leads(id),
                channel TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL,
                logged_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                sequence_id INTEGER,
                step_number INTEGER,
                actor TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            """
        )
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> str:
    return date.today().isoformat()


def _parse_signals(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [s.strip().lower() for s in raw.replace(";", ",").split(",") if s.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(s).strip().lower() for s in raw if str(s).strip()]
    else:
        return []
    seen: list[str] = []
    for item in items:
        if item in ALLOWED_SIGNALS and item not in seen:
            seen.append(item)
    return seen


def validate_signals(raw) -> tuple[list[str], list[str]]:
    """Return (valid, invalid) so callers can reject unknown signals."""
    if raw is None:
        return [], []
    if isinstance(raw, str):
        items = [s.strip().lower() for s in raw.replace(";", ",").split(",") if s.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(s).strip().lower() for s in raw if str(s).strip()]
    else:
        return [], []
    valid = [s for s in dict.fromkeys(items) if s in ALLOWED_SIGNALS]
    invalid = [s for s in dict.fromkeys(items) if s not in ALLOWED_SIGNALS]
    return valid, invalid


def compute_score(role: str, signals: list[str]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    for sig in signals:
        pts = SIGNAL_POINTS.get(sig, 0)
        if pts:
            score += pts
            reasons.append(f"{sig} (+{pts})")
    role_l = (role or "").lower()
    # Word-boundary-ish check: token as a word, or "vp " / "vp," etc.
    role_fit = False
    for tok in ROLE_FIT_TOKENS:
        if re.search(r"(?<![a-z])" + re.escape(tok) + r"(?![a-z])", role_l):
            role_fit = True
            break
    if role_fit:
        score += ROLE_FIT_POINTS
        reasons.append(f"role fit: {role.strip()} (+{ROLE_FIT_POINTS})")
    return min(score, 100), reasons


def _row_to_lead(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["signals"] = json.loads(d["signals"] or "[]")
    d["score_reasons"] = json.loads(d["score_reasons"] or "[]")
    return d


def _find_duplicate(conn, email: str, linkedin_url: str):
    email = (email or "").strip().lower()
    linkedin_url = (linkedin_url or "").strip()
    if email:
        row = conn.execute(
            "SELECT * FROM leads WHERE lower(email) = ?", (email,)
        ).fetchone()
        if row:
            return row
    if linkedin_url:
        row = conn.execute(
            "SELECT * FROM leads WHERE linkedin_url = ?", (linkedin_url,)
        ).fetchone()
        if row:
            return row
    return None


def add_lead(db=None, *, name, company="", role="", email="", linkedin_url="",
             x_handle="", source="", signals=None, notes="") -> dict:
    if not (name or "").strip():
        raise ValueError("name is required")
    valid, invalid = validate_signals(signals or [])
    if invalid:
        raise ValueError(f"unknown signal(s): {', '.join(invalid)}")
    init_db(db)
    with _connect(db) as conn:
        dup = _find_duplicate(conn, email, linkedin_url)
        if dup:
            lead = _row_to_lead(dup)
            lead["duplicate"] = True
            return lead
        score, reasons = compute_score(role, valid)
        now = _now()
        cur = conn.execute(
            """INSERT INTO leads
               (name, company, role, email, linkedin_url, x_handle, source,
                signals, notes, score, score_reasons, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name.strip(), company.strip(), role.strip(), email.strip(),
             linkedin_url.strip(), x_handle.strip(), source.strip(),
             json.dumps(valid), notes.strip(), score, json.dumps(reasons),
             now, now),
        )
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (cur.lastrowid,)).fetchone()
        lead = _row_to_lead(row)
        lead["duplicate"] = False
        return lead


def list_leads(db=None, *, limit: int = 100, min_score: int | None = None) -> list[dict]:
    init_db(db)
    with _connect(db) as conn:
        if min_score is not None:
            rows = conn.execute(
                "SELECT * FROM leads WHERE score >= ? ORDER BY score DESC, id ASC LIMIT ?",
                (min_score, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM leads ORDER BY score DESC, id ASC LIMIT ?", (limit,)
            ).fetchall()
        return [_row_to_lead(r) for r in rows]


def get_lead(db=None, lead_id: int = 0) -> dict | None:
    init_db(db)
    with _connect(db) as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return _row_to_lead(row) if row else None


def score_lead(db=None, lead_id: int = 0) -> dict:
    init_db(db)
    with _connect(db) as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            raise LookupError(f"lead {lead_id} not found")
        lead = _row_to_lead(row)
        score, reasons = compute_score(lead["role"], lead["signals"])
        conn.execute(
            "UPDATE leads SET score = ?, score_reasons = ?, updated_at = ? WHERE id = ?",
            (score, json.dumps(reasons), _now(), lead_id),
        )
        lead["score"] = score
        lead["score_reasons"] = reasons
        return lead


def import_csv(db=None, csv_path: str | Path = "", file_obj=None) -> dict:
    """Import leads from CSV. Returns {imported, skipped_duplicates, errors}."""
    init_db(db)
    if file_obj is not None:
        text = file_obj.read()
        if isinstance(text, bytes):
            text = text.decode("utf-8-sig")
        import io
        reader = csv.DictReader(io.StringIO(text))
    else:
        with open(csv_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        # fall through to shared loop below via rows
        imported = skipped = 0
        errors: list[str] = []
        for i, row in enumerate(rows, start=2):
            try:
                lead = add_lead(
                    db,
                    name=(row.get("name") or "").strip(),
                    company=(row.get("company") or "").strip(),
                    role=(row.get("role") or "").strip(),
                    email=(row.get("email") or "").strip(),
                    linkedin_url=(row.get("linkedin_url") or "").strip(),
                    x_handle=(row.get("x_handle") or "").strip(),
                    source=(row.get("source") or "").strip(),
                    signals=(row.get("signals") or ""),
                    notes=(row.get("notes") or "").strip(),
                )
                if lead.get("duplicate"):
                    skipped += 1
                else:
                    imported += 1
            except Exception as exc:  # noqa: BLE001 - report per-row
                errors.append(f"row {i}: {exc}")
        return {"imported": imported, "skipped_duplicates": skipped, "errors": errors}
    imported = skipped = 0
    errors: list[str] = []
    for i, row in enumerate(reader, start=2):
        try:
            lead = add_lead(
                db,
                name=(row.get("name") or "").strip(),
                company=(row.get("company") or "").strip(),
                role=(row.get("role") or "").strip(),
                email=(row.get("email") or "").strip(),
                linkedin_url=(row.get("linkedin_url") or "").strip(),
                x_handle=(row.get("x_handle") or "").strip(),
                source=(row.get("source") or "").strip(),
                signals=(row.get("signals") or ""),
                notes=(row.get("notes") or "").strip(),
            )
            if lead.get("duplicate"):
                skipped += 1
            else:
                imported += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"row {i}: {exc}")
    return {"imported": imported, "skipped_duplicates": skipped, "errors": errors}


# --- Sequences ---

def _drafts_for_lead(lead: dict) -> list[dict]:
    first = (lead["name"] or "there").strip().split()[0]
    company = lead["company"] or "your company"
    role = lead["role"] or "your team"
    return [
        {
            "step_number": 1, "channel": "linkedin", "kind": "connection_request",
            "draft_text": (
                f"Hi {first} — I noticed {company} and your work as {role}. "
                "I'm building tools for teams like yours at NativeLayer and "
                "would value connecting. No pitch here, just a hello."
            ),
        },
        {
            "step_number": 2, "channel": "linkedin", "kind": "follow_up",
            "draft_text": (
                f"Hi {first}, thanks for connecting. Quick context: NativeLayer helps "
                f"small teams like {company} with practical AI workflows. "
                "Would a short intro call be useful, or is there a better person to speak with?"
            ),
        },
        {
            "step_number": 3, "channel": "email", "kind": "email",
            "draft_text": (
                f"Subject: Quick question for {company}\n\nHi {first},\n\n"
                f"I reached out on LinkedIn — I'm with NativeLayer, and we help teams like {company} "
                "put simple AI workflows in place without a big build.\n\n"
                "Open to a 15-minute intro next week? If not you, who should I talk to?\n\n"
                "Thanks,\nRashad — NativeLayer"
            ),
        },
        {
            "step_number": 4, "channel": "x", "kind": "x_dm",
            "draft_text": (
                f"Hi {first} — saw {company} mentioned in my feed. I'm with NativeLayer, "
                "building practical AI tools for small teams. Happy to share one idea "
                "that might help, if you're open to it."
            ),
        },
    ]


def create_sequence(db=None, lead_id: int = 0, name: str = "") -> dict:
    init_db(db)
    lead = get_lead(db, lead_id)
    if not lead:
        raise LookupError(f"lead {lead_id} not found")
    with _connect(db) as conn:
        now = _now()
        cur = conn.execute(
            "INSERT INTO sequences (lead_id, name, created_at) VALUES (?, ?, ?)",
            (lead_id, name or f"Outreach — {lead['name']}", now),
        )
        seq_id = cur.lastrowid
        for d in _drafts_for_lead(lead):
            conn.execute(
                """INSERT INTO steps (sequence_id, step_number, channel, kind, draft_text, status)
                   VALUES (?, ?, ?, ?, ?, 'draft')""",
                (seq_id, d["step_number"], d["channel"], d["kind"], d["draft_text"]),
            )
    return get_sequence(db, seq_id)


def _row_to_step(row: sqlite3.Row) -> dict:
    return dict(row)


def get_sequence(db=None, sequence_id: int = 0) -> dict | None:
    init_db(db)
    with _connect(db) as conn:
        row = conn.execute("SELECT * FROM sequences WHERE id = ?", (sequence_id,)).fetchone()
        if not row:
            return None
        seq = dict(row)
        steps = conn.execute(
            "SELECT * FROM steps WHERE sequence_id = ? ORDER BY step_number ASC",
            (sequence_id,),
        ).fetchall()
        seq["steps"] = [_row_to_step(s) for s in steps]
        lead = conn.execute("SELECT * FROM leads WHERE id = ?", (seq["lead_id"],)).fetchone()
        seq["lead"] = _row_to_lead(lead) if lead else None
        return seq


def list_sequences(db=None) -> list[dict]:
    init_db(db)
    with _connect(db) as conn:
        rows = conn.execute("SELECT id FROM sequences ORDER BY id ASC").fetchall()
        return [get_sequence(db, r["id"]) for r in rows]


def _audit(conn, event, sequence_id, step_number, actor, detail=""):
    conn.execute(
        """INSERT INTO audit_log (event, sequence_id, step_number, actor, detail, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (event, sequence_id, step_number, actor, detail, _now()),
    )


def approve_step(db=None, sequence_id: int = 0, step_number: int = 0, approver: str = "") -> dict:
    """Human approval gate. Only a 'draft' step can be approved."""
    if not (approver or "").strip():
        raise ValueError("approver is required — a human must approve")
    init_db(db)
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT * FROM steps WHERE sequence_id = ? AND step_number = ?",
            (sequence_id, step_number),
        ).fetchone()
        if not row:
            raise LookupError(f"step {step_number} in sequence {sequence_id} not found")
        if row["status"] != "draft":
            raise ValueError(f"step {step_number} is '{row['status']}', only 'draft' can be approved")
        conn.execute(
            "UPDATE steps SET status = 'approved', approved_by = ?, approved_at = ? "
            "WHERE sequence_id = ? AND step_number = ?",
            (approver.strip(), _now(), sequence_id, step_number),
        )
        _audit(conn, "approve", sequence_id, step_number, approver.strip())
    return get_sequence(db, sequence_id)


def today_sent_counts(db=None, on_date: str | None = None) -> dict:
    init_db(db)
    day = on_date or _today()
    with _connect(db) as conn:
        counts = {ch: 0 for ch in ALLOWED_CHANNELS}
        rows = conn.execute(
            "SELECT channel, COUNT(*) AS n FROM steps WHERE status = 'sent' "
            "AND substr(sent_at, 1, 10) = ? GROUP BY channel",
            (day,),
        ).fetchall()
        for r in rows:
            counts[r["channel"]] = r["n"]
        return counts


def mark_sent(db=None, sequence_id: int = 0, step_number: int = 0, marked_by: str = "") -> dict:
    """Mark a step sent ONLY after human approval and within the daily cap.

    This does NOT send anything. The human sends it themselves outside
    this tool, then marks it here.
    """
    if not (marked_by or "").strip():
        raise ValueError("marked_by is required")
    init_db(db)
    caps = get_caps()
    with _connect(db) as conn:
        row = conn.execute(
            "SELECT * FROM steps WHERE sequence_id = ? AND step_number = ?",
            (sequence_id, step_number),
        ).fetchone()
        if not row:
            raise LookupError(f"step {step_number} in sequence {sequence_id} not found")
        if row["status"] != "approved":
            raise ValueError(
                f"step {step_number} is '{row['status']}' — only an 'approved' step "
                "can be marked sent. Approve it first."
            )
        channel = row["channel"]
        counts = today_sent_counts(db)
        cap = caps.get(channel, 0)
        if counts.get(channel, 0) >= cap:
            raise ValueError(
                f"daily cap reached for {channel}: {counts[channel]}/{cap} sent today"
            )
        conn.execute(
            "UPDATE steps SET status = 'sent', marked_sent_by = ?, sent_at = ? "
            "WHERE sequence_id = ? AND step_number = ?",
            (marked_by.strip(), _now(), sequence_id, step_number),
        )
        _audit(conn, "mark_sent", sequence_id, step_number, marked_by.strip(),
               f"channel={channel}")
    return get_sequence(db, sequence_id)


# --- Replies ---

def log_reply(db=None, *, lead_id: int, channel: str, text: str = "", outcome: str = "") -> dict:
    if channel not in ALLOWED_CHANNELS:
        raise ValueError(f"channel must be one of {sorted(ALLOWED_CHANNELS)}")
    if outcome not in ALLOWED_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(ALLOWED_OUTCOMES)}")
    init_db(db)
    if not get_lead(db, lead_id):
        raise LookupError(f"lead {lead_id} not found")
    with _connect(db) as conn:
        cur = conn.execute(
            "INSERT INTO replies (lead_id, channel, text, outcome, logged_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (lead_id, channel, text.strip(), outcome, _now()),
        )
        row = conn.execute("SELECT * FROM replies WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)


def list_replies(db=None, lead_id: int | None = None) -> list[dict]:
    init_db(db)
    with _connect(db) as conn:
        if lead_id is not None:
            rows = conn.execute(
                "SELECT * FROM replies WHERE lead_id = ? ORDER BY id ASC", (lead_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM replies ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def get_stats(db=None) -> dict:
    init_db(db)
    caps = get_caps()
    with _connect(db) as conn:
        total_leads = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
        avg = conn.execute("SELECT AVG(score) FROM leads").fetchone()[0]
        total_seqs = conn.execute("SELECT COUNT(*) FROM sequences").fetchone()[0]
        step_rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM steps GROUP BY status"
        ).fetchall()
        steps_by_status = {r["status"]: r["n"] for r in step_rows}
        reply_rows = conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM replies GROUP BY outcome"
        ).fetchall()
        replies_by_outcome = {r["outcome"]: r["n"] for r in reply_rows}
    sent = today_sent_counts(db)
    return {
        "leads": total_leads,
        "avg_score": round(float(avg), 1) if avg is not None else 0.0,
        "sequences": total_seqs,
        "steps_by_status": steps_by_status,
        "replies_by_outcome": replies_by_outcome,
        "today_sent": sent,
        "daily_caps": caps,
        "sending": "manual-only — this tool never sends LinkedIn, email, or X messages",
    }


def export_crm(db=None, output_path: str | Path | None = None) -> Path:
    """Write a plain-Markdown CRM file generated from SQLite."""
    init_db(db)
    out = Path(output_path) if output_path else BASE_DIR / "crm" / "OPENCRM.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    leads = list_leads(db, limit=10000)
    seqs = list_sequences(db)
    replies = list_replies(db)
    lines = [
        "# OpenGTM CRM",
        "",
        "Plain-Markdown CRM generated from the local SQLite database. "
        "No database is required to read this file.",
        "",
        f"Generated: {_now()}",
        "",
        "## Accounts",
        "",
    ]
    companies: dict[str, list[dict]] = {}
    for lead in leads:
        companies.setdefault(lead["company"] or "(no company)", []).append(lead)
    for company, members in sorted(companies.items()):
        lines.append(f"### {company}")
        lines.append("")
        for m in members:
            lines.append(
                f"- {m['name']} — {m['role']} — score {m['score']} "
                f"({', '.join(m['score_reasons']) or 'no signals'})"
            )
            if m["email"]:
                lines.append(f"  - Email: {m['email']}")
            if m["linkedin_url"]:
                lines.append(f"  - LinkedIn: {m['linkedin_url']}")
            if m["x_handle"]:
                lines.append(f"  - X: {m['x_handle']}")
            if m["notes"]:
                lines.append(f"  - Notes: {m['notes']}")
        lines.append("")
    lines += ["## People", ""]
    for lead in leads:
        lines.append(
            f"- {lead['name']} ({lead['company']}, {lead['role']}) — "
            f"signals: {', '.join(lead['signals']) or 'none'} — score {lead['score']}"
        )
    lines += ["", "## Activities", ""]
    for seq in seqs:
        lead = seq.get("lead") or {}
        lines.append(f"### Sequence {seq['id']} — {lead.get('name', '')} ({seq['name']})")
        for s in seq["steps"]:
            lines.append(
                f"- Step {s['step_number']} [{s['channel']}] {s['kind']}: {s['status']}"
                + (f" — approved by {s['approved_by']}" if s["approved_by"] else "")
                + (f" — sent by {s['marked_sent_by']}" if s["marked_sent_by"] else "")
            )
        lines.append("")
    for r in replies:
        lines.append(
            f"- Reply (lead {r['lead_id']}, {r['channel']}, {r['outcome']}): {r['text']}"
        )
    lines += ["", "## Tasks", ""]
    pending = 0
    for seq in seqs:
        for s in seq["steps"]:
            if s["status"] == "draft":
                lines.append(
                    f"- [ ] Review + approve step {s['step_number']} "
                    f"({s['channel']}) in sequence {seq['id']}"
                )
                pending += 1
            elif s["status"] == "approved":
                lines.append(
                    f"- [ ] Send step {s['step_number']} "
                    f"({s['channel']}) in sequence {seq['id']} manually, then mark sent"
                )
                pending += 1
    if pending == 0:
        lines.append("- (no pending approvals or sends)")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
