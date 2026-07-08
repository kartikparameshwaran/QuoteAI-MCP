"""Standalone unattended pipeline: the whole flow in one process.

This is the "fire-and-forget" path — no external agent required. Run it
hourly (cron / Azure Function timer / Windows Task Scheduler) and it will:

  1. pull new emails with attachments from the mailbox,
  2. extract each into the Quote schema with Claude,
  3. validate, then submit to the ERP (respecting ERP_MODE),
  4. tag the email processed so the next run skips it.

Prefer this over the agent path when you want deterministic, auditable
automation with no human/agent in the loop. Use the MCP server instead when
you want your existing ChatGPT agent to orchestrate interactively.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .config import AppConfig, ErpConfig, ExtractorConfig, GraphConfig
from .email_client import GraphEmailClient
from .erp_client import ErpClient
from .extractor import QuoteExtractor

log = logging.getLogger("quoteai.pipeline")


@dataclass
class RunSummary:
    scanned: int = 0
    processed: int = 0
    submitted: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def run_once() -> RunSummary:
    app = AppConfig.from_env()
    email = GraphEmailClient(GraphConfig.from_env())
    extractor = QuoteExtractor(ExtractorConfig.from_env())
    erp = ErpClient(ErpConfig.from_env())
    summary = RunSummary()

    try:
        messages = email.list_messages(
            lookback_hours=app.lookback_hours,
            folder=app.mail_folder,
            only_with_attachments=True,
        )
        summary.scanned = len(messages)

        for msg in messages:
            try:
                if email.is_processed(msg.id, app.processed_marker):
                    summary.skipped += 1
                    continue

                attachments = email.get_attachments(msg.id)
                if not attachments:
                    summary.skipped += 1
                    continue

                quote = extractor.extract(msg, attachments)
                if not quote.line_items:
                    log.warning("No line items extracted from %s", msg.subject)
                    summary.skipped += 1
                    continue

                result = erp.submit(quote)
                summary.processed += 1
                if result.ok:
                    summary.submitted += 1
                    log.info(
                        "Submitted quote for '%s' (%s): %s",
                        quote.customer.name,
                        result.mode,
                        result.erp_reference or result.detail,
                    )
                    # Only mark processed on a real submission, not dry runs.
                    if result.mode != "dry_run":
                        try:
                            email.mark_processed(msg.id, app.processed_marker)
                        except Exception as e:  # non-fatal
                            log.warning("Could not tag email processed: %s", e)
                else:
                    summary.failed += 1
                    summary.errors.append(f"{msg.subject}: {result.detail}")
                    log.error("ERP submit failed: %s", result.detail)

            except Exception as e:  # per-message isolation
                summary.failed += 1
                summary.errors.append(f"{msg.subject}: {e}")
                log.exception("Failed processing message %s", msg.subject)
    finally:
        email.close()

    return summary


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    summary = run_once()
    log.info(
        "Run complete: scanned=%d processed=%d submitted=%d skipped=%d failed=%d",
        summary.scanned,
        summary.processed,
        summary.submitted,
        summary.skipped,
        summary.failed,
    )
    for err in summary.errors:
        log.error("  - %s", err)


if __name__ == "__main__":
    main()
