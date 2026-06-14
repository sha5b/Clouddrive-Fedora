# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Microsoft Graph REST client shared by all Microsoft 365 capabilities.

A single instance serves Files (drive enumeration), Mail, and Calendar from the
same OAuth token, supplied lazily by ``token_provider(scopes)`` so the caller
controls auth/refresh (see core.auth.msal_graph). Stage 0: endpoint surface and
method outline; the requests land in stages 3 (files) and 6 (mail/calendar).
"""

from __future__ import annotations

from typing import Callable, Sequence

BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphClient:
    def __init__(self, token_provider: Callable[[Sequence[str]], str]):
        self._token_provider = token_provider

    # -- Files ------------------------------------------------------------
    def list_drives(self) -> list:
        # TODO(stage 3): GET /me/drives  (+ /sites/{id}/drives for SharePoint)
        return []

    # -- Mail -------------------------------------------------------------
    def list_mail_folders(self) -> list:
        # TODO(stage 6): GET /me/mailFolders
        return []

    def list_messages(self, folder_id: str, *, limit: int = 50) -> list:
        # TODO(stage 6): GET /me/mailFolders/{id}/messages?$top={limit}
        return []

    # -- Calendar ---------------------------------------------------------
    def list_calendars(self) -> list:
        # TODO(stage 6): GET /me/calendars
        return []

    def list_events(self, calendar_id: str, start, end) -> list:
        # TODO(stage 6): GET /me/calendars/{id}/calendarView?startDateTime&endDateTime
        return []
