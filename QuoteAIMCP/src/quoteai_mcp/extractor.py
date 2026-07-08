"""LLM-based extraction: email + attachments -> validated Quote JSON.

Only used by the standalone `pipeline.py`. When you drive this from a
ChatGPT/Claude agent through the MCP server, the agent itself performs the
reasoning and simply calls `validate_quote` / `submit_quote` — so you don't
pay for a second model round-trip.

Uses Claude's structured tool-use so the model is forced to return an object
that matches the `Quote` schema, and PDFs are passed natively as document
blocks (no brittle local OCR needed).
"""

from __future__ import annotations

import json
from typing import Optional

from anthropic import Anthropic

from .config import ExtractorConfig
from .email_client import Attachment, EmailMessage
from .schema import Quote, quote_json_schema

_SYSTEM = """You extract structured quote requests for an ERP system.
You are given the text of an email and one or more attachments (PDF, CSV, \
text) that list parts a customer wants quoted. Pull out the customer, the \
line items (part number, quantity, and any price/description), and any \
reference such as an RFQ or PO number.

Rules:
- Only use information present in the email or attachments. Never invent \
part numbers, quantities, or prices.
- If a field is unknown, omit it rather than guessing.
- Combine duplicate parts and preserve requested quantities exactly.
- Always return at least one line item; if none can be found, return the \
extract_quote tool with an empty line_items list so the caller can flag it."""


def _tool_def() -> dict:
    schema = quote_json_schema()
    # Anthropic tool input_schema is a JSON Schema object.
    return {
        "name": "extract_quote",
        "description": "Return the structured quote extracted from the source.",
        "input_schema": schema,
    }


def _attachment_block(att: Attachment) -> Optional[dict]:
    if att.is_pdf:
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": att.as_base64(),
            },
            "title": att.name,
        }
    if att.is_textual:
        return {
            "type": "text",
            "text": f"--- Attachment: {att.name} ---\n{att.as_text()}",
        }
    # Unsupported binary (e.g. .xlsx) — signal it so the model knows.
    return {
        "type": "text",
        "text": (
            f"--- Attachment: {att.name} ({att.content_type}) ---\n"
            "[binary attachment not decoded; convert to CSV/PDF for extraction]"
        ),
    }


class QuoteExtractor:
    def __init__(self, cfg: ExtractorConfig):
        self._cfg = cfg
        self._client = Anthropic(api_key=cfg.api_key)

    def extract(
        self, email: EmailMessage, attachments: list[Attachment]
    ) -> Quote:
        content: list[dict] = [
            {
                "type": "text",
                "text": (
                    f"Email subject: {email.subject}\n"
                    f"From: {email.sender}\n"
                    f"Body preview: {email.body_preview}\n\n"
                    "Extract the quote from the email and attachments below."
                ),
            }
        ]
        for att in attachments:
            block = _attachment_block(att)
            if block:
                content.append(block)

        resp = self._client.messages.create(
            model=self._cfg.model,
            max_tokens=4096,
            system=_SYSTEM,
            tools=[_tool_def()],
            tool_choice={"type": "tool", "name": "extract_quote"},
            messages=[{"role": "user", "content": content}],
        )

        for block in resp.content:
            if block.type == "tool_use" and block.name == "extract_quote":
                quote = Quote.model_validate(block.input)
                quote.source_email_id = email.id
                if attachments:
                    quote.source_attachment = attachments[0].name
                return quote

        raise RuntimeError(
            "Model did not return an extract_quote tool call; raw response: "
            + json.dumps([b.model_dump() for b in resp.content])[:500]
        )
