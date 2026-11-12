"""OpenGTM Engine — FastAPI, port 8040, local only.

No sending, no scraping, no external calls. Steps are drafts until a
human approves them; 'sent' is only marked manually after the human
sends the message themselves outside this tool.
"""
from __future__ import annotations

import io
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

import engine
from config import load_config

app = FastAPI(
    title="OpenGTM Engine",
    description="Clean-room, local-only outbound drafting tool. Drafts only — human sends.",
    version="0.1.0",
)


class LeadIn(BaseModel):
    name: str
    company: str = ""
    role: str = ""
    email: str = ""
    linkedin_url: str = ""
    x_handle: str = ""
    source: str = ""
    signals: list[str] = Field(default_factory=list)
    notes: str = ""


class SequenceIn(BaseModel):
    lead_id: int
    name: str = ""


class ApproveIn(BaseModel):
    step_number: int
    approver: str


class MarkSentIn(BaseModel):
    step_number: int
    marked_by: str


class ReplyIn(BaseModel):
    lead_id: int
    channel: str
    text: str = ""
    outcome: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "open-gtm-engine", "sending": "manual-only"}


@app.get("/api/leads")
def api_list_leads(limit: int = 100, min_score: int | None = None):
    return engine.list_leads(limit=limit, min_score=min_score)


@app.post("/api/leads", status_code=201)
def api_add_lead(payload: LeadIn):
    try:
        return engine.add_lead(
            name=payload.name, company=payload.company, role=payload.role,
            email=payload.email, linkedin_url=payload.linkedin_url,
            x_handle=payload.x_handle, source=payload.source,
            signals=payload.signals, notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/leads/{lead_id}")
def api_get_lead(lead_id: int):
    lead = engine.get_lead(lead_id=lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@app.post("/api/leads/import")
async def api_import_leads(file: UploadFile = File(...)):
    raw = await file.read()
    result = engine.import_csv(file_obj=io.BytesIO(raw))
    return result


@app.post("/api/leads/{lead_id}/score")
def api_score_lead(lead_id: int):
    try:
        return engine.score_lead(lead_id=lead_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/sequences")
def api_list_sequences():
    return engine.list_sequences()


@app.post("/api/sequences", status_code=201)
def api_create_sequence(payload: SequenceIn):
    try:
        return engine.create_sequence(lead_id=payload.lead_id, name=payload.name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/sequences/{sequence_id}")
def api_get_sequence(sequence_id: int):
    seq = engine.get_sequence(sequence_id=sequence_id)
    if not seq:
        raise HTTPException(status_code=404, detail="sequence not found")
    return seq


@app.post("/api/sequences/{sequence_id}/approve-step")
def api_approve_step(sequence_id: int, payload: ApproveIn):
    try:
        return engine.approve_step(
            sequence_id=sequence_id, step_number=payload.step_number,
            approver=payload.approver,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/sequences/{sequence_id}/mark-sent")
def api_mark_sent(sequence_id: int, payload: MarkSentIn):
    try:
        return engine.mark_sent(
            sequence_id=sequence_id, step_number=payload.step_number,
            marked_by=payload.marked_by,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Approval-gate and daily-cap failures are client errors, not 500s.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/replies")
def api_list_replies(lead_id: int | None = None):
    return engine.list_replies(lead_id=lead_id)


@app.post("/api/replies", status_code=201)
def api_log_reply(payload: ReplyIn):
    try:
        return engine.log_reply(
            lead_id=payload.lead_id, channel=payload.channel,
            text=payload.text, outcome=payload.outcome,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/stats")
def api_stats():
    return engine.get_stats()


@app.post("/api/crm/export")
def api_export_crm():
    path = engine.export_crm()
    return {"path": str(path), "file": "crm/OPENCRM.md"}


@app.get("/api/crm/export", response_class=PlainTextResponse)
def api_export_crm_get():
    path = engine.export_crm()
    return Path(path).read_text(encoding="utf-8")


@app.get("/api/config")
def api_config():
    return load_config()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=load_config()["port"])
