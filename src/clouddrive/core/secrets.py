# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Secret storage via libsecret (Secret Service portal inside Flatpak).

OAuth/MSAL token caches are stored here, never in plaintext on disk. Inside the
Flatpak sandbox libsecret's simple API transparently uses the Secret Service
portal with a per-app local keyring — no broad secrets D-Bus hole needed.

Stage 0: thin wrapper with the intended API. The libsecret schema/collection
wiring is filled in alongside the auth layer (stage 2). See docs/AUTH.md.
"""

from __future__ import annotations

from typing import Optional

SCHEMA_NAME = "com.fiberelements.Clouddrive.Token"


class SecretStore:
    """Stores/retrieves per-account secrets keyed by (account_id, kind)."""

    def store(self, account_id: str, kind: str, value: str) -> None:
        # TODO(stage 2): use Secret.password_store_sync with a Secret.Schema
        # describing {"account": str, "kind": str}.
        raise NotImplementedError("secret storage lands in stage 2")

    def lookup(self, account_id: str, kind: str) -> Optional[str]:
        # TODO(stage 2): Secret.password_lookup_sync(...)
        raise NotImplementedError("secret storage lands in stage 2")

    def clear(self, account_id: str, kind: str) -> None:
        # TODO(stage 2): Secret.password_clear_sync(...)
        raise NotImplementedError("secret storage lands in stage 2")
