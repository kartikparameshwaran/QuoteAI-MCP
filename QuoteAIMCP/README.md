# QuoteAI‑MCP

Automate the flow you do by hand today:

> **Email (with attachments) → structured quote JSON → your ERP‑connected website → Visual ERP builds the quote**

You already built the app that pushes values into Visual ERP. This project
automates the two manual steps in the middle: **creating the JSON object**
from an incoming email's attachments, and **submitting it** to the website
that feeds the ERP.

---

## Will MCP work for this? — Yes, with one nuance

**MCP (Model Context Protocol) is the right layer for the *tools*, but it is
not the scheduler and not the reasoning.** It's worth being precise:

| Piece | What does it | Where it lives |
|-------|-------------|----------------|
| **Reasoning** (attachment → JSON) | the LLM | your ChatGPT/Claude agent, *or* `extractor.py` |
| **Tools** (read email, validate, submit) | **MCP server** | `server.py` (this repo) |
| **Schedule** ("run hourly") | a trigger | ChatGPT scheduled task / cron / Azure Function |

So MCP absolutely works — it gives your existing hourly ChatGPT agent
*hands*: instead of you reading the email and pasting JSON, the agent calls
`list_quote_emails`, `get_email_content`, `validate_quote`, and
`submit_quote`. MCP does **not** replace the hourly trigger or the model's
reasoning; it standardizes the tools they use.

Because of that, this repo ships **two ways to run**, sharing the same core:

1. **MCP server** (`quoteai_mcp/server.py`) — connect it to your ChatGPT (or
   Claude) agent as a connector. The agent orchestrates; MCP does the I/O.
2. **Standalone pipeline** (`quoteai_mcp/pipeline.py`) — no agent needed. A
   single hourly process reads mail, extracts with Claude, validates, and
   submits. **More deterministic and auditable for true unattended
   automation** — recommended if you don't need a human/agent in the loop.

Use whichever fits. They share `schema.py`, `email_client.py`, and
`erp_client.py`, so the JSON shape and ERP behavior are identical either way.

---

## Architecture

```
                 ┌─────────────────────────── shared core ───────────────────────────┐
                 │  schema.py   email_client.py (Graph)   erp_client.py   extractor.py │
                 └────────────────────────────────────────────────────────────────────┘
        MCP path                                        Standalone path
  ChatGPT/Claude agent                              cron / Azure Function (hourly)
        │  (MCP tools)                                       │
        ▼                                                    ▼
   server.py  ── list_quote_emails                     pipeline.run_once()
              ── get_email_content                       1. list emails
              ── get_quote_schema                        2. extract w/ Claude
              ── validate_quote                          3. validate
              ── submit_quote  ──► ERP website ◄──       4. submit  ─► ERP website
              ── mark_email_processed                    5. mark processed
```

---

## The quote schema

`src/quoteai_mcp/schema.py` defines the exact JSON object. **Edit it to
match what your Visual ERP quote builder consumes** — that one file keeps the
agent, the extractor, and the submitter in sync. Shape today:

```jsonc
{
  "customer": { "name": "...", "customer_number": "...", "email": "...", ... },
  "line_items": [
    { "part_number": "PN-100", "description": "...", "quantity": 10,
      "unit_of_measure": "EA", "unit_price": 3.25, "required_date": "2026-08-01" }
  ],
  "reference": "RFQ-8891",
  "currency": "USD",
  "notes": "...",
  "source_email_id": "...", "source_attachment": "rfq.pdf"
}
```

---

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill it in
```

Fill in `.env`:

- **Azure AD app** — register an app, grant application permission
  `Mail.Read` (+ `Mail.ReadWrite` for the mark-processed step),
  admin-consent it. Put tenant/client id + secret and the target mailbox UPN
  in `.env`.
- **`ANTHROPIC_API_KEY`** — only needed for the standalone pipeline.
- **ERP submission** — pick a mode:
  - `ERP_MODE=dry_run` (default) — validate + log, submit nothing. Start here.
  - `ERP_MODE=api` — set `ERP_API_URL` (+ optional `ERP_API_TOKEN`). **Best
    option** if your website exposes/could expose an endpoint.
  - `ERP_MODE=browser` — replicates pasting JSON into the page. Set
    `ERP_WEB_URL`, `ERP_JSON_SELECTOR`, `ERP_SUBMIT_SELECTOR`, then
    `pip install playwright && playwright install chromium`.

---

## Run it

**Standalone, once (safe to start — defaults to dry_run):**
```bash
python scripts/run_hourly.py
```

**Hourly cron:**
```
0 * * * *  /path/.venv/bin/python /path/scripts/run_hourly.py >> /var/log/quoteai.log 2>&1
```

**As an MCP server (stdio) for a local agent:**
```bash
python -m quoteai_mcp.server
```

**Connect to ChatGPT / Claude as a connector** — point the client at the
`quoteai-mcp` command (installed via `pip install -e .`). Example Claude
Desktop `mcpServers` entry:
```jsonc
{
  "mcpServers": {
    "quoteai": {
      "command": "quoteai-mcp",
      "env": { "AZURE_TENANT_ID": "...", "AZURE_CLIENT_ID": "...",
               "AZURE_CLIENT_SECRET": "...", "GRAPH_MAILBOX": "quotes@yourco.com",
               "ERP_MODE": "api", "ERP_API_URL": "https://..." }
    }
  }
}
```
Then prompt the agent: *"Check for new quote emails, extract each into the
quote schema, validate, and submit."* It will chain the tools itself.

---

## Tests

```bash
pytest -q
```

---

## What you still need to plug in

These are the intentional, documented seams — the code has clear spots for
each:

1. **`schema.py`** — make the fields exactly match your Visual ERP quote
   payload.
2. **ERP submission** — confirm whether your website has an API (`api` mode,
   preferred) or must be driven in a browser (`browser` mode); set the
   selectors if browser.
3. **Azure app permissions** — `Mail.Read` at minimum; `Mail.ReadWrite` to
   auto-tag processed emails.

Start in `dry_run`, confirm the JSON matches what you used to paste, then
flip `ERP_MODE` to `api` or `browser`.
