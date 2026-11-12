# OpenGTM Engine — Tasks, saved for later

Saved 2026-11-12 by Rashad's "execute the most necessary set of tasks (save my tasks for later)".
Nothing in this file is built yet. Each item needs its own tap before work starts.

## Done — Phase 1 (2026-11-12, verified)

- Local-only engine: CSV/manual lead intake with dedup, deterministic intent
  scoring 0–100, 4-step draft-only sequences, hard human-approval gate,
  daily caps (LinkedIn 30, email 50, X 20), own MCP server + FastAPI REST API,
  Markdown CRM export, manual reply inbox.
- 22/22 pytest, live API smoke (health + stats 200, manual-only), approval
  gate and daily cap proven live.
- Public repo live: https://github.com/9ether530-byte/open-gtm-engine
  (MIT, head commit `c726d9b0` at publish; README + this file follow).

## Next, in order — most necessary first

### 1. First real use (no code, Rashad-side)
Import a real lead list of his own, score it, draft sequences for NativeLayer,
send approved steps himself. Proves the tool on real work before any Phase 2
code. Done when: at least 10 real leads scored and 1 approved sequence sent
manually, with replies logged.

### 2. Reply → meeting tracking + local stats view
Add outcome tracking (reply → meeting booked → deal) and a simple local HTML
stats page. No external calls. Gate: tap + decide which outcomes matter.
Done when: stats endpoint/page shows replies and meetings, tests pass.

### 3. Sequence templates per niche
Curated draft templates for NativeLayer B2B, Unseen Library, and one other
niche he picks. Templates only — no sending change. Gate: tap + niche pick.

### 4. Gmail drafts only (never auto-send)
Create Gmail drafts via OAuth for approved email steps; the human presses
Send in Gmail. No auto-send, no bulk. Gate: tap + OAuth setup his-side +
explicit approval of the Gmail scope. If OAuth is refused, this stays unbuilt.

### 5. CI on GitHub
Add `.github/workflows/ci.yml` (pytest on push). Note: the Muse GitHub App
lacks Workflows permission, so this file must be added from a PC clone or
the GitHub web UI. Gate: tap, then add via that route.

### 6. Public launch polish
Repo topics, a v0.1.0 release, and a short launch note. Gate: tap, after
task 1 proves real use. No paid promotion, no outreach sent from this tool.

## Explicitly NOT tasks (do not build)

- LinkedIn auto-send, LinkedIn scraping, session-cookie driving.
- A buyer database or enrichment — scores stay user-supplied only.
- Copying PumpGTM code, branding, logo, or name; calling any PumpGTM service.
- Any sending without a human approval gate, or above the daily caps.

## Kill criteria

Stop / pivot if: no real lead list is run through it within 30 days, or the
approval gate is ever bypassed, or a platform restricts an account for
outreach drafted with it — then re-check the ToS warning in the README
before any further sending work.
