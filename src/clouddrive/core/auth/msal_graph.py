# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Microsoft Graph authentication via MSAL.

Public-client (no secret) device-code or auth-code+PKCE flow. The MSAL
SerializableTokenCache is persisted into libsecret (core.secrets). Always
request ``offline_access`` and refresh silently with ``acquire_token_silent``.

Stage 0: scope/endpoint constants and the intended API surface. The MSAL calls
land in stage 2. See docs/AUTH.md for app-registration steps.
"""

from __future__ import annotations

from typing import Sequence

AUTHORITY = "https://login.microsoftonline.com/common"
NATIVE_REDIRECT_URI = "https://login.microsoftonline.com/common/oauth2/nativeclient"

# Delegated scopes. Request only the subset a given module needs.
SCOPES_FILES = ["Files.ReadWrite.All", "Sites.ReadWrite.All"]
SCOPES_MAIL = ["Mail.ReadWrite", "Calendars.ReadWrite", "Contacts.ReadWrite"]
SCOPES_BASE = ["User.Read"]  # offline_access/openid/profile added by MSAL


class GraphAuth:
    def __init__(self, client_id: str, secrets, account_id: str):
        self._client_id = client_id
        self._secrets = secrets
        self._account_id = account_id

    def sign_in_device_code(self, scopes: Sequence[str]) -> dict:
        # TODO(stage 2): msal.PublicClientApplication(...).initiate_device_flow()
        # then acquire_token_by_device_flow(); persist the token cache.
        raise NotImplementedError("MSAL flow lands in stage 2")

    def acquire_token_silent(self, scopes: Sequence[str]) -> str | None:
        raise NotImplementedError("MSAL flow lands in stage 2")
