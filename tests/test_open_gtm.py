"""OpenGTM Engine Phase 1 tests — local only, temp SQLite per test."""
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import engine  # noqa: E402
from engine import (  # noqa: E402
    add_lead, approve_step, compute_score, create_sequence, export_crm,
    get_lead, get_sequence, get_stats, import_csv, list_leads, list_replies,
    log_reply, mark_sent, score_lead,
)


@pytest.fixture
def db(tmp_path, monkeypatch):
    p = tmp_path / "test.db"
    monkeypatch.setenv("OPENGTM_DB_PATH", str(p))
    engine.init_db(p)
    return p


@pytest.fixture
def tiny_caps(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"daily_caps": {"linkedin": 1, "email": 1, "x": 1}}))
    monkeypatch.setenv("OPENGTM_CONFIG_PATH", str(cfg))
    return cfg


def _lead(db, **kw):
    base = dict(name="Ada Example", company="Example Analytics", role="Founder",
                email="ada@example.test", signals=["hiring"])
    base.update(kw)
    return add_lead(db, **base)


# --- Scoring ---

def test_scoring_hiring_plus_founder():
    score, reasons = compute_score("Founder", ["hiring"])
    assert score == 40  # 25 + 15
    assert any("hiring" in r for r in reasons)


def test_scoring_all_signals_caps_at_100():
    score, reasons = compute_score("CEO", ["hiring", "funding", "post_engagement", "competitor_customer"])
    assert score == 100  # 25+25+20+15+15 = 100
    assert len(reasons) == 5


def test_scoring_no_role_fit_no_signals():
    score, reasons = compute_score("Marketing Manager", [])
    assert score == 0
    assert reasons == []


def test_scoring_role_tokens():
    assert compute_score("VP Sales", [])[0] == 15
    assert compute_score("Director of Operations", [])[0] == 15
    assert compute_score("Head of Growth", [])[0] == 15
    assert compute_score("Intern", [])[0] == 0


def test_score_lead_stores_score_and_reasons(db):
    lead = _lead(db, signals=["funding", "post_engagement"])
    assert lead["score"] == 60  # 25+20+15 role
    assert "funding (+25)" in lead["score_reasons"]
    rescored = score_lead(db, lead["id"])
    assert rescored["score"] == 60


def test_unknown_signal_rejected(db):
    with pytest.raises(ValueError, match="unknown signal"):
        _lead(db, email="x@example.test", signals=["telepathy"])


# --- Dedupe / import ---

def test_dedupe_by_email(db):
    a = _lead(db)
    b = _lead(db, name="Ada Duplicate", company="Other Co")
    assert b["id"] == a["id"]
    assert b["duplicate"] is True
    assert len(list_leads(db)) == 1


def test_dedupe_by_linkedin_url(db):
    a = _lead(db, email="one@example.test",
              linkedin_url="https://www.linkedin.com/in/ada-example")
    b = _lead(db, email="two@example.test",
              linkedin_url="https://www.linkedin.com/in/ada-example")
    assert b["id"] == a["id"]
    assert len(list_leads(db)) == 1


def test_csv_import_and_duplicate_skip(db, tmp_path):
    csv_path = tmp_path / "leads.csv"
    csv_path.write_text(
        "name,company,role,email,linkedin_url,x_handle,source,signals,notes\n"
        "Ada Example,Example Analytics,Founder,ada@example.test,,@ada,manual,\"hiring;funding\",\n"
        "Ben Sample,Sample Co,Director,ben@example.test,,@ben,manual,post_engagement,\n"
        "Ada Example,Example Analytics,Founder,ada@example.test,,@ada,manual,hiring,\n"
    )
    result = import_csv(db, csv_path=csv_path)
    assert result == {"imported": 2, "skipped_duplicates": 1, "errors": []}
    assert len(list_leads(db)) == 2


def test_csv_import_via_file_object(db):
    text = ("name,company,role,email,linkedin_url,x_handle,source,signals,notes\n"
            "Cara Test,Testbridge Labs,VP Sales,cara@example.test,,@cara,manual,funding,\n")
    result = import_csv(db, file_obj=io.BytesIO(text.encode()))
    assert result["imported"] == 1
    assert list_leads(db)[0]["score"] == 40


def test_sample_leads_csv_imports_five(db):
    root = Path(__file__).parent.parent
    result = import_csv(db, csv_path=root / "sample_leads.csv")
    assert result == {"imported": 5, "skipped_duplicates": 0, "errors": []}


# --- Sequences / approval gate / caps ---

def test_sequence_draft_generation(db):
    lead = _lead(db)
    seq = create_sequence(db, lead["id"])
    assert len(seq["steps"]) == 4
    assert [s["step_number"] for s in seq["steps"]] == [1, 2, 3, 4]
    assert [s["channel"] for s in seq["steps"]] == ["linkedin", "linkedin", "email", "x"]
    assert all(s["status"] == "draft" for s in seq["steps"])
    assert all(s["draft_text"] for s in seq["steps"])
    assert lead["name"].split()[0] in seq["steps"][0]["draft_text"]


def test_approval_gate_blocks_unapproved_mark_sent(db):
    lead = _lead(db)
    seq = create_sequence(db, lead["id"])
    with pytest.raises(ValueError, match="only an 'approved' step"):
        mark_sent(db, seq["id"], 1, "Rashad")
    # Step is still a draft after the failed attempt.
    assert get_sequence(db, seq["id"])["steps"][0]["status"] == "draft"


def test_approve_then_mark_sent(db):
    lead = _lead(db)
    seq = create_sequence(db, lead["id"])
    approved = approve_step(db, seq["id"], 1, "Rashad")
    assert approved["steps"][0]["status"] == "approved"
    assert approved["steps"][0]["approved_by"] == "Rashad"
    sent = mark_sent(db, seq["id"], 1, "Rashad")
    assert sent["steps"][0]["status"] == "sent"
    # Cannot approve a sent step again.
    with pytest.raises(ValueError, match="only 'draft' can be approved"):
        approve_step(db, seq["id"], 1, "Rashad")


def test_approve_requires_human(db):
    lead = _lead(db)
    seq = create_sequence(db, lead["id"])
    with pytest.raises(ValueError, match="approver is required"):
        approve_step(db, seq["id"], 1, "")


def test_daily_cap_blocks_over_limit(db, tiny_caps):
    # linkedin cap = 1 in tiny_caps fixture.
    l1 = _lead(db, email="one@example.test")
    l2 = _lead(db, name="Ben Sample", email="two@example.test")
    s1 = create_sequence(db, l1["id"])
    s2 = create_sequence(db, l2["id"])
    approve_step(db, s1["id"], 1, "Rashad")
    approve_step(db, s2["id"], 1, "Rashad")
    mark_sent(db, s1["id"], 1, "Rashad")
    with pytest.raises(ValueError, match="daily cap reached for linkedin"):
        mark_sent(db, s2["id"], 1, "Rashad")


def test_create_sequence_unknown_lead(db):
    with pytest.raises(LookupError):
        create_sequence(db, 9999)


# --- Replies / stats / CRM ---

def test_reply_logging_and_outcomes(db):
    lead = _lead(db)
    r = log_reply(db, lead_id=lead["id"], channel="linkedin",
                  text="Interested, book a call", outcome="meeting_booked")
    assert r["outcome"] == "meeting_booked"
    assert len(list_replies(db, lead_id=lead["id"])) == 1
    with pytest.raises(ValueError, match="outcome must be"):
        log_reply(db, lead_id=lead["id"], channel="linkedin", outcome="maybe")
    with pytest.raises(ValueError, match="channel must be"):
        log_reply(db, lead_id=lead["id"], channel="carrier-pigeon", outcome="replied")


def test_stats_counts(db):
    lead = _lead(db)
    create_sequence(db, lead["id"])
    log_reply(db, lead_id=lead["id"], channel="email", outcome="replied", text="hi")
    stats = get_stats(db)
    assert stats["leads"] == 1
    assert stats["sequences"] == 1
    assert stats["steps_by_status"]["draft"] == 4
    assert stats["replies_by_outcome"]["replied"] == 1
    assert stats["daily_caps"]["linkedin"] == 30
    assert "manual-only" in stats["sending"]


def test_export_crm_writes_markdown(db, tmp_path):
    lead = _lead(db)
    seq = create_sequence(db, lead["id"])
    log_reply(db, lead_id=lead["id"], channel="x", outcome="no_reply", text="")
    out = tmp_path / "OPENCRM.md"
    path = export_crm(db, output_path=out)
    text = Path(path).read_text()
    assert "# OpenGTM CRM" in text
    assert "Example Analytics" in text
    assert "Ada Example" in text
    assert "## Tasks" in text
    assert "Review + approve step 1" in text


# --- API smoke ---

def test_api_smoke(db, monkeypatch):
    from fastapi.testclient import TestClient

    import app as app_module

    client = TestClient(app_module.app)
    # Note: the API uses the default DB path (env OPENGTM_DB_PATH is set by fixture),
    # so this exercises the same temp DB.
    r = client.get("/health")
    assert r.status_code == 200
    r = client.post("/api/leads", json={
        "name": "API Person", "company": "API Co", "role": "Founder",
        "email": "api@example.test", "signals": ["hiring"]})
    assert r.status_code == 201
    assert r.json()["score"] == 40
    lead_id = r.json()["id"]
    r = client.get(f"/api/leads/{lead_id}")
    assert r.status_code == 200
    r = client.get("/api/stats")
    assert r.status_code == 200
    assert r.json()["leads"] >= 1
    # Approval gate via API.
    r = client.post("/api/sequences", json={"lead_id": lead_id})
    assert r.status_code == 201
    seq_id = r.json()["id"]
    r = client.post(f"/api/sequences/{seq_id}/mark-sent",
                    json={"step_number": 1, "marked_by": "Rashad"})
    assert r.status_code == 400  # unapproved
    r = client.post(f"/api/sequences/{seq_id}/approve-step",
                    json={"step_number": 1, "approver": "Rashad"})
    assert r.status_code == 200
    r = client.post(f"/api/sequences/{seq_id}/mark-sent",
                    json={"step_number": 1, "marked_by": "Rashad"})
    assert r.status_code == 200
    assert r.json()["steps"][0]["status"] == "sent"


def test_mcp_tools_list_via_stdio(db):
    root = Path(__file__).parent.parent
    env = dict(os.environ, OPENGTM_DB_PATH=str(db))
    proc = subprocess.run(
        [sys.executable, "mcp_server.py"],
        input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',
        capture_output=True, text=True, cwd=str(root), env=env, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    resp = json.loads(proc.stdout.strip().splitlines()[-1])
    names = [t["name"] for t in resp["result"]["tools"]]
    assert names == ["list_leads", "get_lead", "score_lead", "create_sequence",
                     "get_sequence", "approve_step", "list_replies", "log_reply", "get_stats"]
