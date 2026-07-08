"""Submit a validated Quote to your ERP-connected website.

Three modes (set ERP_MODE):
  - "dry_run" : validate + return the payload, submit nothing. Safe default.
  - "api"     : HTTP POST the JSON to ERP_API_URL. Cleanest if your web app
                exposes an endpoint (recommended).
  - "browser" : replicate the manual "paste into the website" step with
                Playwright — navigate, fill the JSON field, click submit.

The browser path exists because you described *pasting JSON into a website*.
If that website has (or can add) a real endpoint, prefer "api" — it is far
more reliable for unattended automation than driving a headless browser.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .config import ErpConfig
from .schema import Quote


@dataclass
class SubmitResult:
    ok: bool
    mode: str
    detail: str
    payload: dict = field(default_factory=dict)
    erp_reference: Optional[str] = None


def _payload(quote: Quote) -> dict:
    if quote.quote_date is None:
        quote = quote.model_copy(update={"quote_date": dt.date.today()})
    # mode="json" makes dates/decimals JSON-serializable.
    return quote.model_dump(mode="json", exclude_none=True)


class ErpClient:
    def __init__(self, cfg: ErpConfig):
        self._cfg = cfg

    def submit(self, quote: Quote) -> SubmitResult:
        payload = _payload(quote)
        mode = self._cfg.mode.lower()
        if mode == "dry_run":
            return SubmitResult(
                ok=True,
                mode="dry_run",
                detail="Validated only (ERP_MODE=dry_run); nothing submitted.",
                payload=payload,
            )
        if mode == "api":
            return self._submit_api(payload)
        if mode == "browser":
            return self._submit_browser(payload)
        return SubmitResult(
            ok=False,
            mode=mode,
            detail=f"Unknown ERP_MODE '{mode}'. Use dry_run | api | browser.",
            payload=payload,
        )

    def _submit_api(self, payload: dict) -> SubmitResult:
        if not self._cfg.api_url:
            return SubmitResult(
                False, "api", "ERP_API_URL is not set.", payload
            )
        headers = {"Content-Type": "application/json"}
        if self._cfg.api_token:
            headers["Authorization"] = f"Bearer {self._cfg.api_token}"
        try:
            resp = httpx.post(
                self._cfg.api_url, json=payload, headers=headers, timeout=120
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            return SubmitResult(False, "api", f"ERP API error: {e}", payload)

        ref = None
        try:
            data = resp.json()
            ref = data.get("quoteId") or data.get("id") or data.get("reference")
        except Exception:
            pass
        return SubmitResult(
            ok=True,
            mode="api",
            detail=f"Submitted to ERP API (HTTP {resp.status_code}).",
            payload=payload,
            erp_reference=ref,
        )

    def _submit_browser(self, payload: dict) -> SubmitResult:
        if not self._cfg.web_url:
            return SubmitResult(
                False, "browser", "ERP_WEB_URL is not set.", payload
            )
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return SubmitResult(
                False,
                "browser",
                "playwright not installed. Run: pip install playwright && "
                "playwright install chromium",
                payload,
            )

        json_text = json.dumps(payload, indent=2)
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self._cfg.headless)
                page = browser.new_page()
                page.goto(self._cfg.web_url, wait_until="networkidle")
                page.fill(self._cfg.json_selector, json_text)
                page.click(self._cfg.submit_selector)
                page.wait_for_load_state("networkidle")
                # Grab any visible confirmation text for the audit trail.
                confirmation = page.inner_text("body")[:500]
                browser.close()
        except Exception as e:
            return SubmitResult(
                False, "browser", f"Browser automation error: {e}", payload
            )
        return SubmitResult(
            ok=True,
            mode="browser",
            detail="Pasted JSON into the website and clicked submit.",
            payload=payload,
            erp_reference=None,
        )
