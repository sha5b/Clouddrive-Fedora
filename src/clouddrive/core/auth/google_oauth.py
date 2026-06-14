# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Google OAuth2 for the Gmail and Calendar APIs.

Installed-app / loopback flow; refresh token stored in libsecret. Stage 0:
constants + API surface; the flow lands in stage 6. See docs/AUTH.md.
"""

from __future__ import annotations

from typing import Sequence

SCOPES_MAIL = ["https://www.googleapis.com/auth/gmail.modify"]
SCOPES_CALENDAR = ["https://www.googleapis.com/auth/calendar"]
SCOPES_BASE = ["openid", "email", "profile"]


class GoogleAuth:
    def __init__(self, client_id: str, client_secret: str, secrets, account_id: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._secrets = secrets
        self._account_id = account_id

    def sign_in(self, scopes: Sequence[str]) -> dict:
        raise NotImplementedError("Google OAuth flow lands in stage 6")

    def access_token(self) -> str | None:
        raise NotImplementedError("Google OAuth flow lands in stage 6")
