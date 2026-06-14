# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Registry of configured accounts.

Analogous to Alpaca's ``instance_manager``. Holds account metadata (non-secret),
emits change notifications the UI binds to. Secrets live in core.secrets; this
class only stores identifiers and display state.

Stage 0: in-memory skeleton with the intended API. Stage 1 persists to GSettings
and connects to the auth layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from gi.repository import GObject


@dataclass
class Account:
    id: str
    display_name: str
    provider: str  # "microsoft" | "google"
    module_id: str  # which module owns it, e.g. "onedrive"


class AccountRegistry(GObject.Object):
    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, settings):
        super().__init__()
        self._settings = settings
        self._accounts: Dict[str, Account] = {}

    def accounts(self) -> List[Account]:
        return list(self._accounts.values())

    def add(self, account: Account) -> None:
        self._accounts[account.id] = account
        self.emit("changed")

    def remove(self, account_id: str) -> None:
        if self._accounts.pop(account_id, None) is not None:
            self.emit("changed")
