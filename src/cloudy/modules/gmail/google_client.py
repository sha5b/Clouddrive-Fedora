# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Gmail + Google Calendar REST client.

Returns the same normalized dict shapes as the Microsoft GraphClient so the
Mail/Calendar views are provider-agnostic:

  message: {id, subject, from, received, preview, is_read}
  event:   {id, subject, start, end, location, all_day}

Tokens are supplied lazily by ``token_provider(scopes)`` (see
core.auth.google_oauth).
"""

from __future__ import annotations

import base64
import html
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Callable, Sequence

from ...core.auth.google_oauth import SCOPES_CALENDAR, SCOPES_MAIL

GMAIL = "https://gmail.googleapis.com/gmail/v1"
CALENDAR = "https://www.googleapis.com/calendar/v3"


class GoogleError(Exception):
    pass


def _decode_b64url(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _extract_rich(payload: dict) -> tuple[str, bool]:
    """Walk a Gmail payload, preferring text/html. Returns (content, is_html).

    The reader renders HTML, so we surface the richest body we can find and
    fall back to text/plain only when there's no HTML alternative.
    """
    mime = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")
    if mime == "text/html" and data:
        return _decode_b64url(data), True
    if mime == "text/plain" and data:
        return _decode_b64url(data), False

    html_part = ""
    text_part = ""
    for part in payload.get("parts", []):
        content, is_html = _extract_rich(part)
        if not content:
            continue
        if is_html and not html_part:
            html_part = content
        elif not is_html and not text_part:
            text_part = content
    if html_part:
        return html_part, True
    return text_part, False


class GoogleClient:
    def __init__(self, token_provider: Callable[[Sequence[str]], str | None]):
        self._token_provider = token_provider

    def _get(self, url: str, scopes: Sequence[str]) -> dict:
        token = self._token_provider(scopes)
        if not token:
            raise GoogleError("not signed in (no token for the requested scopes)")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise GoogleError(f"Google {exc.code}: {exc.read().decode(errors='replace')}") from exc

    def _post(self, url: str, body: dict | None, scopes: Sequence[str]) -> dict:
        token = self._token_provider(scopes)
        if not token:
            raise GoogleError("not signed in (no token for the requested scopes)")
        data = json.dumps(body).encode() if body is not None else b""
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raise GoogleError(f"Google {exc.code}: {exc.read().decode(errors='replace')}") from exc

    # -- Mail (Gmail) -----------------------------------------------------
    # Friendly names + display order for Gmail's system labels; user-created
    # labels follow, alphabetically.
    _SYSTEM_LABELS = [
        ("INBOX", "Inbox"), ("STARRED", "Starred"), ("IMPORTANT", "Important"),
        ("SENT", "Sent"), ("DRAFT", "Drafts"), ("SPAM", "Spam"), ("TRASH", "Trash"),
    ]

    def list_folders(self) -> list[dict]:
        """Provider-agnostic folder list: ``[{id, name, unread}]`` (Gmail labels).

        Gmail's ``labels.list`` carries no unread counts, so ``unread`` is 0;
        the curated system labels lead, then user labels alphabetically.
        """
        data = self._get(f"{GMAIL}/users/me/labels", SCOPES_MAIL)
        by_id = {lab["id"]: lab for lab in data.get("labels", [])}
        out = []
        for lid, name in self._SYSTEM_LABELS:
            if lid in by_id:
                out.append({"id": lid, "name": name, "unread": 0})
        user = sorted(
            (lab for lab in data.get("labels", []) if lab.get("type") == "user"),
            key=lambda lab: lab.get("name", "").lower(),
        )
        for lab in user:
            out.append({"id": lab["id"], "name": lab.get("name", ""), "unread": 0})
        return out

    def list_messages(self, folder_id: str = "INBOX", *, limit: int = 15) -> list[dict]:
        listing = self._get(
            f"{GMAIL}/users/me/messages?labelIds={folder_id}&maxResults={limit}",
            SCOPES_MAIL,
        )
        out = []
        for ref in listing.get("messages", []):
            msg = self._get(
                f"{GMAIL}/users/me/messages/{ref['id']}"
                f"?format=metadata&metadataHeaders=Subject&metadataHeaders=From",
                SCOPES_MAIL,
            )
            out.append(self._message_from_json(msg))
        return out

    @staticmethod
    def _message_from_json(msg: dict) -> dict:
        headers = {
            h["name"].lower(): h["value"]
            for h in msg.get("payload", {}).get("headers", [])
        }
        received = ""
        internal = msg.get("internalDate")
        if internal:
            received = datetime.fromtimestamp(
                int(internal) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        labels = msg.get("labelIds", [])
        # Gmail's snippet (and occasionally header values) are HTML-escaped
        # ('&amp;', '&#39;', …); decode so plain Gtk.Labels read naturally.
        return {
            "id": msg.get("id", ""),
            "subject": html.unescape(headers.get("subject", "(no subject)")),
            "from": html.unescape(headers.get("from", "")),
            "received": received,
            "preview": html.unescape(msg.get("snippet", "")),
            "is_read": "UNREAD" not in labels,
            "important": "IMPORTANT" in labels,
            "starred": "STARRED" in labels,
        }

    def get_message(self, message_id: str) -> dict:
        data = self._get(f"{GMAIL}/users/me/messages/{message_id}?format=full", SCOPES_MAIL)
        payload = data.get("payload", {})
        headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
        received = ""
        if data.get("internalDate"):
            received = datetime.fromtimestamp(
                int(data["internalDate"]) / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        content, is_html = _extract_rich(payload)
        if not content:
            content, is_html = html.unescape(data.get("snippet", "")), False
        return {
            "id": data.get("id", message_id),
            "subject": html.unescape(headers.get("subject", "(no subject)")),
            "from": html.unescape(headers.get("from", "")),
            "to": html.unescape(headers.get("to", "")),
            "received": received,
            "body": content,
            "body_html": is_html,
        }

    def mark_read(self, message_id: str, read: bool = True) -> None:
        """Mark a message read/unread by toggling the UNREAD label (gmail.modify)."""
        body = {"removeLabelIds": ["UNREAD"]} if read else {"addLabelIds": ["UNREAD"]}
        self._post(f"{GMAIL}/users/me/messages/{message_id}/modify", body, SCOPES_MAIL)

    def delete_message(self, message_id: str) -> None:
        """Move a message to Trash (recoverable; needs gmail.modify)."""
        self._post(f"{GMAIL}/users/me/messages/{message_id}/trash", None, SCOPES_MAIL)

    # -- Calendar ---------------------------------------------------------
    def list_events(self, start_iso: str, end_iso: str, *, limit: int = 50) -> list[dict]:
        params = urllib.parse.urlencode({
            "timeMin": start_iso,
            "timeMax": end_iso,
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": str(limit),
        })
        data = self._get(f"{CALENDAR}/calendars/primary/events?{params}", SCOPES_CALENDAR)
        out = []
        for e in data.get("items", []):
            start = e.get("start", {})
            end = e.get("end", {})
            all_day = "date" in start
            out.append({
                "id": e.get("id", ""),
                "subject": e.get("summary", "(no title)"),
                "start": start.get("dateTime") or start.get("date", ""),
                "end": end.get("dateTime") or end.get("date", ""),
                "location": e.get("location", ""),
                "all_day": all_day,
            })
        return out
