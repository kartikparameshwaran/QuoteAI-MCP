"""Read email + attachments from a Microsoft 365 mailbox via Graph API.

Auth uses the client-credentials flow (app-only), which is the right choice
for an unattended hourly job. Register an app in Azure AD with the
`Mail.Read` (and optionally `Mail.ReadWrite` if you want the "mark as
processed" step) application permission and admin-consent it.
"""

from __future__ import annotations

import base64
import datetime as dt
from dataclasses import dataclass
from typing import Optional

import httpx
import msal

from .config import GraphConfig

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_SCOPE = ["https://graph.microsoft.com/.default"]

# Attachment content types we can hand to the extractor as text/binary.
_TEXTUAL = {
    "text/plain",
    "text/csv",
    "application/json",
    "application/xml",
    "text/xml",
}


@dataclass
class Attachment:
    id: str
    name: str
    content_type: str
    content_bytes: bytes

    @property
    def is_pdf(self) -> bool:
        return self.content_type == "application/pdf" or self.name.lower().endswith(
            ".pdf"
        )

    @property
    def is_textual(self) -> bool:
        return self.content_type in _TEXTUAL or self.name.lower().endswith(
            (".txt", ".csv", ".json", ".xml")
        )

    def as_text(self) -> str:
        """Best-effort decode for textual attachments."""
        return self.content_bytes.decode("utf-8", errors="replace")

    def as_base64(self) -> str:
        return base64.b64encode(self.content_bytes).decode("ascii")


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender: str
    received: str
    body_preview: str
    has_attachments: bool
    attachments: list[Attachment]


class GraphEmailClient:
    def __init__(self, cfg: GraphConfig):
        self._cfg = cfg
        self._app = msal.ConfidentialClientApplication(
            client_id=cfg.client_id,
            authority=f"https://login.microsoftonline.com/{cfg.tenant_id}",
            client_credential=cfg.client_secret,
        )
        self._client = httpx.Client(timeout=60)

    def _token(self) -> str:
        result = self._app.acquire_token_silent(_SCOPE, account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=_SCOPE)
        if "access_token" not in result:
            raise RuntimeError(
                f"Failed to acquire Graph token: {result.get('error_description', result)}"
            )
        return result["access_token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}"}

    def list_messages(
        self,
        lookback_hours: int = 1,
        folder: str = "Inbox",
        only_with_attachments: bool = True,
        unread_only: bool = False,
    ) -> list[EmailMessage]:
        """List recent messages (metadata only; attachments fetched lazily)."""
        since = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        filters = [f"receivedDateTime ge {since}"]
        if only_with_attachments:
            filters.append("hasAttachments eq true")
        if unread_only:
            filters.append("isRead eq false")

        url = (
            f"{GRAPH_BASE}/users/{self._cfg.mailbox}/mailFolders/{folder}/messages"
        )
        params = {
            "$filter": " and ".join(filters),
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,hasAttachments",
            "$top": "25",
        }
        resp = self._client.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()

        messages = []
        for item in resp.json().get("value", []):
            sender = (
                item.get("from", {})
                .get("emailAddress", {})
                .get("address", "")
            )
            messages.append(
                EmailMessage(
                    id=item["id"],
                    subject=item.get("subject", ""),
                    sender=sender,
                    received=item.get("receivedDateTime", ""),
                    body_preview=item.get("bodyPreview", ""),
                    has_attachments=item.get("hasAttachments", False),
                    attachments=[],
                )
            )
        return messages

    def get_attachments(self, message_id: str) -> list[Attachment]:
        """Download all file attachments for a message."""
        url = (
            f"{GRAPH_BASE}/users/{self._cfg.mailbox}"
            f"/messages/{message_id}/attachments"
        )
        resp = self._client.get(url, headers=self._headers())
        resp.raise_for_status()

        out: list[Attachment] = []
        for att in resp.json().get("value", []):
            if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue  # skip item/reference attachments
            raw = att.get("contentBytes", "")
            out.append(
                Attachment(
                    id=att["id"],
                    name=att.get("name", "attachment"),
                    content_type=att.get("contentType", "application/octet-stream"),
                    content_bytes=base64.b64decode(raw) if raw else b"",
                )
            )
        return out

    def mark_processed(
        self, message_id: str, category: str, mark_read: bool = True
    ) -> None:
        """Tag a message so the next hourly run skips it. Requires
        Mail.ReadWrite. Safe to call best-effort."""
        url = f"{GRAPH_BASE}/users/{self._cfg.mailbox}/messages/{message_id}"
        body = {"categories": [category]}
        if mark_read:
            body["isRead"] = True
        resp = self._client.patch(url, headers=self._headers(), json=body)
        resp.raise_for_status()

    def is_processed(self, message_id: str, category: str) -> bool:
        url = f"{GRAPH_BASE}/users/{self._cfg.mailbox}/messages/{message_id}"
        resp = self._client.get(
            url, headers=self._headers(), params={"$select": "categories"}
        )
        resp.raise_for_status()
        return category in resp.json().get("categories", [])

    def close(self) -> None:
        self._client.close()
