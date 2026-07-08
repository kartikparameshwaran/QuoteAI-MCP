"""QuoteAI MCP server.

Exposes the email + ERP capabilities as MCP tools so a ChatGPT or Claude
agent can run the whole "email -> JSON -> ERP quote" flow by calling tools
instead of a human doing it by hand.

Tools exposed:
  - list_quote_emails         : recent emails (with attachments) to process
  - get_email_content         : email body + attachment text/PDF for one message
  - get_quote_schema          : the exact JSON Schema the agent must produce
  - validate_quote            : check a candidate JSON against the schema
  - submit_quote              : push a validated quote to the ERP website
  - mark_email_processed      : tag an email so the next run skips it

Run it:
  python -m quoteai_mcp.server            # stdio transport (local agents)
The FastMCP object is also importable as `mcp` for other transports.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import AppConfig, ErpConfig, GraphConfig
from .email_client import GraphEmailClient
from .erp_client import ErpClient
from .schema import Quote, quote_json_schema

mcp = FastMCP("quoteai-mcp")

# Lazily built so `import` / schema tools work without full credentials.
_email: GraphEmailClient | None = None
_erp: ErpClient | None = None


def _email_client() -> GraphEmailClient:
    global _email
    if _email is None:
        _email = GraphEmailClient(GraphConfig.from_env())
    return _email


def _erp_client() -> ErpClient:
    global _erp
    if _erp is None:
        _erp = ErpClient(ErpConfig.from_env())
    return _erp


@mcp.tool()
def get_quote_schema() -> dict:
    """Return the JSON Schema of the quote object the ERP expects.

    Produce JSON that validates against this before calling submit_quote.
    """
    return quote_json_schema()


@mcp.tool()
def list_quote_emails(lookback_hours: int = 1) -> list[dict]:
    """List recent emails that have attachments and may contain quote requests.

    Returns id, subject, sender, received time and a body preview for each.
    Use get_email_content(message_id) to pull the full content to extract.
    """
    app = AppConfig.from_env()
    client = _email_client()
    msgs = client.list_messages(
        lookback_hours=lookback_hours or app.lookback_hours,
        folder=app.mail_folder,
        only_with_attachments=True,
    )
    out = []
    for m in msgs:
        already = False
        try:
            already = client.is_processed(m.id, app.processed_marker)
        except Exception:
            pass
        out.append(
            {
                "message_id": m.id,
                "subject": m.subject,
                "sender": m.sender,
                "received": m.received,
                "body_preview": m.body_preview,
                "already_processed": already,
            }
        )
    return out


@mcp.tool()
def get_email_content(message_id: str) -> dict:
    """Return an email's attachments so you can extract the quote.

    Textual attachments (csv/txt/json/xml) are returned inline as text.
    PDFs and other binaries are returned base64-encoded with their media
    type so you can read or forward them.
    """
    client = _email_client()
    attachments = client.get_attachments(message_id)
    result: dict[str, Any] = {"message_id": message_id, "attachments": []}
    for att in attachments:
        entry: dict[str, Any] = {
            "name": att.name,
            "content_type": att.content_type,
        }
        if att.is_textual:
            entry["text"] = att.as_text()
        else:
            entry["base64"] = att.as_base64()
        result["attachments"].append(entry)
    return result


@mcp.tool()
def validate_quote(quote_json: dict | str) -> dict:
    """Validate a candidate quote object against the ERP schema.

    Returns {"valid": true, "normalized": {...}} on success, or
    {"valid": false, "errors": "..."} describing what to fix.
    """
    if isinstance(quote_json, str):
        try:
            quote_json = json.loads(quote_json)
        except json.JSONDecodeError as e:
            return {"valid": False, "errors": f"Not valid JSON: {e}"}
    try:
        quote = Quote.model_validate(quote_json)
    except Exception as e:
        return {"valid": False, "errors": str(e)}
    return {"valid": True, "normalized": quote.model_dump(mode="json", exclude_none=True)}


@mcp.tool()
def submit_quote(quote_json: dict | str) -> dict:
    """Validate and submit a quote to the ERP-connected website.

    Honors ERP_MODE (dry_run | api | browser). Returns the outcome and the
    exact payload that was (or would be) submitted, plus any ERP reference.
    """
    if isinstance(quote_json, str):
        try:
            quote_json = json.loads(quote_json)
        except json.JSONDecodeError as e:
            return {"ok": False, "detail": f"Not valid JSON: {e}"}
    try:
        quote = Quote.model_validate(quote_json)
    except Exception as e:
        return {"ok": False, "detail": f"Schema validation failed: {e}"}

    result = _erp_client().submit(quote)
    return {
        "ok": result.ok,
        "mode": result.mode,
        "detail": result.detail,
        "erp_reference": result.erp_reference,
        "payload": result.payload,
    }


@mcp.tool()
def mark_email_processed(message_id: str) -> dict:
    """Tag an email as processed so future hourly runs skip it.

    Requires the Graph app to have Mail.ReadWrite permission.
    """
    app = AppConfig.from_env()
    try:
        _email_client().mark_processed(message_id, app.processed_marker)
    except Exception as e:
        return {"ok": False, "detail": str(e)}
    return {"ok": True, "detail": f"Tagged '{app.processed_marker}'."}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
