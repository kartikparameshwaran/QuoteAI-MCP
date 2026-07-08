"""Central configuration, loaded from environment variables.

Nothing secret is hard-coded. Copy `.env.example` to `.env`, fill it in,
and either export the vars or let `python-dotenv` load them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # optional convenience
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            "See .env.example for the full list."
        )
    return val


@dataclass(frozen=True)
class GraphConfig:
    """Microsoft Graph (Azure / Microsoft 365 mailbox) settings.

    Uses the OAuth2 client-credentials flow, so you register an app in
    Azure AD, grant it Mail.Read (application permission), and drop the
    tenant/client id + secret here. `mailbox` is the UPN of the mailbox to
    read (e.g. quotes@yourco.com).
    """

    tenant_id: str
    client_id: str
    client_secret: str
    mailbox: str

    @classmethod
    def from_env(cls) -> "GraphConfig":
        return cls(
            tenant_id=_require("AZURE_TENANT_ID"),
            client_id=_require("AZURE_CLIENT_ID"),
            client_secret=_require("AZURE_CLIENT_SECRET"),
            mailbox=_require("GRAPH_MAILBOX"),
        )


@dataclass(frozen=True)
class ExtractorConfig:
    """LLM extraction settings (used only by the standalone pipeline;
    when driven from a ChatGPT/Claude agent, the agent does extraction)."""

    api_key: str
    model: str

    @classmethod
    def from_env(cls) -> "ExtractorConfig":
        return cls(
            api_key=_require("ANTHROPIC_API_KEY"),
            model=os.getenv("EXTRACTOR_MODEL", "claude-sonnet-5"),
        )


@dataclass(frozen=True)
class ErpConfig:
    """ERP submission settings.

    mode = "api"     -> POST the quote JSON to ERP_API_URL (recommended if
                        your website exposes an endpoint).
    mode = "browser" -> drive the website with Playwright: navigate to
                        ERP_WEB_URL, paste JSON into the field identified by
                        ERP_JSON_SELECTOR, and click ERP_SUBMIT_SELECTOR.
    mode = "dry_run" -> validate + log only, submit nothing (safe default).
    """

    mode: str
    api_url: str
    api_token: str
    web_url: str
    json_selector: str
    submit_selector: str
    headless: bool

    @classmethod
    def from_env(cls) -> "ErpConfig":
        return cls(
            mode=os.getenv("ERP_MODE", "dry_run"),
            api_url=os.getenv("ERP_API_URL", ""),
            api_token=os.getenv("ERP_API_TOKEN", ""),
            web_url=os.getenv("ERP_WEB_URL", ""),
            json_selector=os.getenv("ERP_JSON_SELECTOR", "#quote-json"),
            submit_selector=os.getenv("ERP_SUBMIT_SELECTOR", "#submit-quote"),
            headless=os.getenv("ERP_HEADLESS", "true").lower() != "false",
        )


@dataclass(frozen=True)
class AppConfig:
    lookback_hours: int
    mail_folder: str
    processed_marker: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            lookback_hours=int(os.getenv("LOOKBACK_HOURS", "1")),
            mail_folder=os.getenv("MAIL_FOLDER", "Inbox"),
            processed_marker=os.getenv("PROCESSED_CATEGORY", "QuoteProcessed"),
        )
