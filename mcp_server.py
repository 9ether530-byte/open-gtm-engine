"""OpenGTM Engine — MCP server over stdio (JSON-RPC 2.0).

Own tools only; tool names are generic concepts, not copies of any
other product's tool list. The server reads/writes the same local
SQLite database as the REST API and CLI. It never sends messages,
never scrapes, and never calls an external service.

Run:  python mcp_server.py
Protocol: one JSON object per line on stdin, one per line on stdout.
Methods: initialize, ping, tools/list, tools/call
"""
from __future__ import annotations

import json
import sys

import engine

TOOLS = [
    {
        "name": "list_leads",
        "description": "List leads, highest intent score first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 100},
                "min_score": {"type": "integer"},
            },
        },
    },
    {
        "name": "get_lead",
        "description": "Get one lead by id, including score and reasons.",
        "inputSchema": {
            "type": "object",
            "properties": {"lead_id": {"type": "integer"}},
            "required": ["lead_id"],
        },
    },
    {
        "name": "score_lead",
        "description": "Recompute a lead's deterministic intent score (0-100) with reasons.",
        "inputSchema": {
            "type": "object",
            "properties": {"lead_id": {"type": "integer"}},
            "required": ["lead_id"],
        },
    },
    {
        "name": "create_sequence",
        "description": "Create a 4-step draft-only outreach sequence for a lead. Drafts only; nothing is sent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer"},
                "name": {"type": "string"},
            },
            "required": ["lead_id"],
        },
    },
    {
        "name": "get_sequence",
        "description": "Get a sequence with its steps and their draft/approved/sent status.",
        "inputSchema": {
            "type": "object",
            "properties": {"sequence_id": {"type": "integer"}},
            "required": ["sequence_id"],
        },
    },
    {
        "name": "approve_step",
        "description": "Human-approve one draft step. A step cannot be marked sent until approved.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sequence_id": {"type": "integer"},
                "step_number": {"type": "integer"},
                "approver": {"type": "string"},
            },
            "required": ["sequence_id", "step_number", "approver"],
        },
    },
    {
        "name": "list_replies",
        "description": "List manually logged replies, optionally for one lead.",
        "inputSchema": {
            "type": "object",
            "properties": {"lead_id": {"type": "integer"}},
        },
    },
    {
        "name": "log_reply",
        "description": "Manually log a reply (human read it and recorded it). No inbox is read automatically.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lead_id": {"type": "integer"},
                "channel": {"type": "string", "enum": ["linkedin", "email", "x"]},
                "text": {"type": "string"},
                "outcome": {"type": "string",
                            "enum": ["replied", "meeting_booked", "not_interested", "no_reply"]},
            },
            "required": ["lead_id", "channel", "outcome"],
        },
    },
    {
        "name": "get_stats",
        "description": "Counts, steps by status, replies by outcome, today's sent totals vs daily caps.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _call_tool(name: str, args: dict):
    if name == "list_leads":
        return engine.list_leads(limit=args.get("limit", 100), min_score=args.get("min_score"))
    if name == "get_lead":
        lead = engine.get_lead(lead_id=args["lead_id"])
        if not lead:
            raise LookupError("lead not found")
        return lead
    if name == "score_lead":
        return engine.score_lead(lead_id=args["lead_id"])
    if name == "create_sequence":
        return engine.create_sequence(lead_id=args["lead_id"], name=args.get("name", ""))
    if name == "get_sequence":
        seq = engine.get_sequence(sequence_id=args["sequence_id"])
        if not seq:
            raise LookupError("sequence not found")
        return seq
    if name == "approve_step":
        return engine.approve_step(
            sequence_id=args["sequence_id"], step_number=args["step_number"],
            approver=args["approver"])
    if name == "list_replies":
        return engine.list_replies(lead_id=args.get("lead_id"))
    if name == "log_reply":
        return engine.log_reply(
            lead_id=args["lead_id"], channel=args["channel"],
            text=args.get("text", ""), outcome=args["outcome"])
    if name == "get_stats":
        return engine.get_stats()
    raise ValueError(f"unknown tool: {name}")


def _handle(req: dict) -> dict:
    method = req.get("method")
    req_id = req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "open-gtm-engine", "version": "0.1.0"},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = _call_tool(name, args)
        except (ValueError, LookupError) as exc:
            return {"jsonrpc": "2.0", "id": req_id, "error": {
                "code": -32000, "message": str(exc)}}
        return {"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result, default=str)}]}}
    return {"jsonrpc": "2.0", "id": req_id, "error": {
        "code": -32601, "message": f"method not found: {method}"}}


def main() -> None:
    engine.init_db()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        resp = _handle(req)
        sys.stdout.write(json.dumps(resp, default=str) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
