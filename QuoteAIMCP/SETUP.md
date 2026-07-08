# Setup — plain-English walkthrough

You do **not** need to understand how Azure or Infor VISUAL work internally.
You only need to fill in a handful of values. This guide walks each one.

---

## 0. Install (one time)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                # you'll edit .env in the steps below
```

---

## 1. Azure — this is ONLY used to read your mailbox

The app logs into your Microsoft 365 mailbox to fetch incoming quote emails.
To let it do that, you register an "app identity" in Azure once. Ask whoever
administers your Microsoft 365 / Azure to do this if you don't have admin
rights — it takes ~5 minutes.

1. Go to **portal.azure.com** → search **"App registrations"** → **New registration**.
   - Name: `QuoteAI Mailbox Reader` → Register.
2. On the app's **Overview** page, copy two values into `.env`:
   - **Directory (tenant) ID** → `AZURE_TENANT_ID`
   - **Application (client) ID** → `AZURE_CLIENT_ID`
3. Left menu → **Certificates & secrets** → **New client secret** → copy the
   secret **Value** (not the ID) into `.env` → `AZURE_CLIENT_SECRET`.
   *(You can't view it again later, so copy it now.)*
4. Left menu → **API permissions** → **Add a permission** → **Microsoft Graph**
   → **Application permissions** → search and check **`Mail.Read`**
   (add **`Mail.ReadWrite`** too if you want emails auto-tagged as processed)
   → **Add permissions** → then click **Grant admin consent**.
5. In `.env`, set `GRAPH_MAILBOX` to the mailbox address to watch, e.g.
   `quotes@yourcompany.com`.

That's all the Azure you need. The code handles the rest.

---

## 2. Anthropic key — only for the standalone (hands-off) mode

If you'll run it fully automatically (no ChatGPT agent in the loop), the
extraction of parts/customer from attachments is done by Claude. Get a key
from **console.anthropic.com** and set `ANTHROPIC_API_KEY` in `.env`.

*(If instead you connect this to your existing ChatGPT agent as an MCP
connector, the agent does the extraction and you can skip this key.)*

---

## 3. ERP — how the JSON gets to VISUAL

The code never talks to Infor VISUAL directly. It hands the finished JSON to
**the website/app you already built** that feeds VISUAL. You just tell it
*how* to hand it over. Ask whoever built that website **one question**:

> "Does it have a URL I can send data to, or do I paste into a page?"

Then set `ERP_MODE` in `.env`:

| Their answer | `ERP_MODE` | Also set |
|---|---|---|
| "It has an endpoint/URL for data" | `api` | `ERP_API_URL` (+ `ERP_API_TOKEN` if it needs a key) |
| "You paste JSON into a page" | `browser` | `ERP_WEB_URL`, `ERP_JSON_SELECTOR`, `ERP_SUBMIT_SELECTOR` (the box + button on the page) |
| Not sure yet / want to test first | `dry_run` | nothing — it just prints the JSON so you can eyeball it |

**Start with `dry_run`.** Run it, confirm the printed JSON matches what you
used to paste by hand, *then* switch to `api` or `browser`.

For `browser` mode only, also run:
```bash
pip install playwright && playwright install chromium
```

---

## 4. Match the JSON to your quote

Open `src/quoteai_mcp/schema.py`. It defines the exact fields (customer +
line items). Edit them so they match what your VISUAL quote builder expects.
This one file keeps everything in sync.

---

## 5. Run it

**Test once (safe — dry_run prints, submits nothing):**
```bash
python scripts/run_hourly.py
```

**Then schedule hourly** (cron example):
```
0 * * * *  /full/path/.venv/bin/python /full/path/scripts/run_hourly.py >> quoteai.log 2>&1
```

**Or run as an MCP server for your ChatGPT/Claude agent:**
```bash
python -m quoteai_mcp.server
```
See `README.md` for connecting it to an agent.

---

## Quick checklist

- [ ] `.env` filled: Azure 4 values, mailbox, (Anthropic key if standalone)
- [ ] `ERP_MODE` chosen (start `dry_run`)
- [ ] `schema.py` fields match your VISUAL quote
- [ ] `python scripts/run_hourly.py` prints correct JSON
- [ ] switch `ERP_MODE` to `api` / `browser`
- [ ] schedule hourly
