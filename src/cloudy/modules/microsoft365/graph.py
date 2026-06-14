# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Microsoft Graph REST client shared by all Microsoft 365 capabilities.

A single instance serves Files (drive/site enumeration, share links), Mail, and
Calendar from the same OAuth token, supplied lazily by ``token_provider(scopes)``
so the caller controls auth/refresh (see core.auth.msal_graph).

Files enumeration and share links are implemented here; mail/calendar land in
stage 6.
"""

from __future__ import annotations

import html
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Sequence

from ...core.auth.msal_graph import SCOPES_FILES, SCOPES_MAIL, SCOPES_TEAMS

BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphError(Exception):
    pass


@dataclass
class Drive:
    """A OneDrive/SharePoint drive (document library)."""

    id: str
    name: str
    kind: str  # "personal" | "business" | "documentLibrary"
    web_url: str
    site_id: str = ""  # set for SharePoint/Teams libraries


class GraphClient:
    def __init__(self, token_provider: Callable[[Sequence[str]], str | None]):
        self._token_provider = token_provider

    # -- low-level --------------------------------------------------------
    def _get(self, path: str, scopes: Sequence[str], headers: dict | None = None) -> dict:
        token = self._token_provider(scopes)
        if not token:
            raise GraphError("not signed in (no token for the requested scopes)")
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        hdrs = {"Authorization": f"Bearer {token}"}
        if headers:
            hdrs.update(headers)
        req = urllib.request.Request(url, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise GraphError(f"Graph {exc.code}: {detail}") from exc

    def _post(self, path: str, body: dict, scopes: Sequence[str]) -> dict:
        return self._write("POST", path, body, scopes)

    def _patch(self, path: str, body: dict, scopes: Sequence[str]) -> dict:
        return self._write("PATCH", path, body, scopes)

    def _write(self, method: str, path: str, body: dict | None,
               scopes: Sequence[str]) -> dict:
        token = self._token_provider(scopes)
        if not token:
            raise GraphError("not signed in (no token for the requested scopes)")
        url = f"{BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {token}"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise GraphError(f"Graph {exc.code}: {detail}") from exc

    def _delete(self, path: str, scopes: Sequence[str]) -> None:
        token = self._token_provider(scopes)
        if not token:
            raise GraphError("not signed in (no token for the requested scopes)")
        req = urllib.request.Request(
            f"{BASE_URL}{path}", method="DELETE",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30):
                return
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise GraphError(f"Graph {exc.code}: {detail}") from exc

    # -- Files: drives & sites -------------------------------------------
    def list_drives(self) -> list[Drive]:
        """The user's own drives (personal OneDrive / business)."""
        data = self._get("/me/drives", SCOPES_FILES)
        return [self._drive_from_json(d) for d in data.get("value", [])]

    def search_sites(self, query: str) -> list[dict]:
        """Search SharePoint sites (for Teams/SharePoint libraries)."""
        q = urllib.parse.quote(query)
        data = self._get(f"/sites?search={q}", SCOPES_FILES)
        return [
            {"id": s["id"], "name": s.get("displayName", s.get("name", "")),
             "web_url": s.get("webUrl", "")}
            for s in data.get("value", [])
        ]

    def site_by_path(self, hostname: str, site_path: str) -> dict:
        """Resolve a site from a hostname + server-relative path."""
        data = self._get(f"/sites/{hostname}:{site_path}", SCOPES_FILES)
        return {"id": data["id"], "name": data.get("displayName", ""),
                "web_url": data.get("webUrl", "")}

    def list_site_drives(self, site_id: str) -> list[Drive]:
        """Document libraries of a SharePoint site (Teams files live here)."""
        data = self._get(f"/sites/{site_id}/drives", SCOPES_FILES)
        drives = []
        for d in data.get("value", []):
            drive = self._drive_from_json(d)
            drive.site_id = site_id
            drives.append(drive)
        return drives

    def list_teams(self) -> list[Drive]:
        """Each Team the user belongs to, as its default document library (drive).

        We mount at the **team level** (the team's Files root), not channels or
        subfolders. Requires the Team.ReadBasic.All scope.
        """
        data = self._get("/me/joinedTeams", SCOPES_TEAMS)
        out = []
        for team in data.get("value", []):
            team_id = team.get("id")
            if not team_id:
                continue
            try:
                d = self._get(f"/groups/{team_id}/drive", SCOPES_FILES)
            except GraphError:
                continue  # some teams have no provisioned files / no access
            drive = self._drive_from_json(d)
            # Show the TEAM name; fall back if displayName is empty/missing.
            drive.name = team.get("displayName") or drive.name or "Untitled Team"
            drive.kind = "team"
            out.append(drive)
        return out

    def create_share_link(self, drive_id: str, item_id: str, *, editable: bool = False) -> str:
        body = {"type": "edit" if editable else "view", "scope": "organization"}
        data = self._post(
            f"/drives/{drive_id}/items/{item_id}/createLink", body, SCOPES_FILES
        )
        return data.get("link", {}).get("webUrl", "")

    @staticmethod
    def _drive_from_json(d: dict) -> Drive:
        return Drive(
            id=d["id"],
            name=d.get("name", d.get("driveType", "drive")),
            kind=d.get("driveType", "documentLibrary"),
            web_url=d.get("webUrl", ""),
        )

    # -- Mail -------------------------------------------------------------
    # Surface the everyday folders first; everything else falls in alphabetically.
    _FOLDER_PRIORITY = {
        "Inbox": 0, "Drafts": 1, "Sent Items": 2, "Archive": 3,
        "Deleted Items": 4, "Junk Email": 5, "Outbox": 6,
    }

    def list_folders(self) -> list[dict]:
        """Provider-agnostic folder list: ``[{id, name, unread}]``, inbox first."""
        folders = self.list_mail_folders()
        folders.sort(
            key=lambda f: (self._FOLDER_PRIORITY.get(f["name"], 99), f["name"].lower())
        )
        return folders

    def list_mail_folders(self) -> list[dict]:
        data = self._get("/me/mailFolders?$top=50", SCOPES_MAIL)
        return [
            {"id": f["id"], "name": f.get("displayName", ""),
             "unread": f.get("unreadItemCount", 0)}
            for f in data.get("value", [])
        ]

    def list_messages(self, folder_id: str = "inbox", *, limit: int = 25) -> list[dict]:
        # Keep $/commas literal (Graph-friendly); only the space in the orderby
        # value needs encoding (a raw space makes urllib reject the URL).
        orderby = urllib.parse.quote("receivedDateTime desc")
        path = (
            f"/me/mailFolders/{folder_id}/messages"
            f"?$top={limit}"
            f"&$select=subject,from,receivedDateTime,bodyPreview,isRead,importance,flag"
            f"&$orderby={orderby}"
        )
        data = self._get(path, SCOPES_MAIL)
        out = []
        for m in data.get("value", []):
            sender = (
                m.get("from", {}).get("emailAddress", {}) if m.get("from") else {}
            )
            out.append({
                "id": m["id"],
                "subject": html.unescape(m.get("subject", "(no subject)")),
                "from": html.unescape(sender.get("name") or sender.get("address", "")),
                "received": m.get("receivedDateTime", ""),
                "preview": html.unescape(m.get("bodyPreview", "")),
                "is_read": m.get("isRead", True),
                "important": m.get("importance") == "high",
                "starred": (m.get("flag") or {}).get("flagStatus") == "flagged",
            })
        return out

    def get_message(self, message_id: str) -> dict:
        """Full message; ``body`` is the original HTML when available.

        We deliberately do *not* ask Graph for a text body anymore — the reader
        renders the real HTML, so we keep the formatting/links/images intact.
        """
        data = self._get(
            f"/me/messages/{message_id}"
            f"?$select=subject,from,toRecipients,receivedDateTime,body",
            SCOPES_MAIL,
        )
        sender = (data.get("from") or {}).get("emailAddress", {})
        to = ", ".join(
            r.get("emailAddress", {}).get("address", "")
            for r in data.get("toRecipients", [])
        )
        body = data.get("body") or {}
        return {
            "id": data.get("id", message_id),
            "subject": html.unescape(data.get("subject", "(no subject)")),
            "from": html.unescape(sender.get("name") or sender.get("address", "")),
            "to": html.unescape(to),
            "received": data.get("receivedDateTime", ""),
            "body": body.get("content", ""),
            "body_html": body.get("contentType") == "html",
        }

    def mark_read(self, message_id: str, read: bool = True) -> None:
        """Set the read/unread state of a message (needs Mail.ReadWrite)."""
        self._patch(f"/me/messages/{message_id}", {"isRead": read}, SCOPES_MAIL)

    def delete_message(self, message_id: str) -> None:
        """Move a message to Deleted Items (Graph DELETE is recoverable)."""
        self._delete(f"/me/messages/{message_id}", SCOPES_MAIL)

    # -- Calendar ---------------------------------------------------------
    def list_calendars(self) -> list[dict]:
        data = self._get("/me/calendars?$top=50", SCOPES_MAIL)
        return [
            {"id": c["id"], "name": c.get("name", "")}
            for c in data.get("value", [])
        ]

    def list_events(self, start_iso: str, end_iso: str, *, limit: int = 50) -> list[dict]:
        """Calendar view between two ISO-8601 UTC timestamps."""
        params = urllib.parse.urlencode({
            "startDateTime": start_iso,
            "endDateTime": end_iso,
            "$orderby": "start/dateTime",
            "$top": str(limit),
            "$select": "subject,start,end,location,isAllDay",
        })
        data = self._get(f"/me/calendarView?{params}", SCOPES_MAIL)
        out = []
        for e in data.get("value", []):
            out.append({
                "id": e["id"],
                "subject": e.get("subject", "(no title)"),
                "start": e.get("start", {}).get("dateTime", ""),
                "end": e.get("end", {}).get("dateTime", ""),
                "location": (e.get("location") or {}).get("displayName", ""),
                "all_day": e.get("isAllDay", False),
            })
        return out
