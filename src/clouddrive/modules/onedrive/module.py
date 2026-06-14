# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""OneDrive / SharePoint / Teams module.

Orchestrates host backends (abraunegg ``onedrive`` for selective sync;
``onedriver``/``rclone`` for on-demand). This is an orchestration layer, not a
sync engine. See docs/MODULES.md and docs/ARCHITECTURE.md.

Stage 0: implements the interface with stubbed behavior so the shell can list
and toggle it. Real subprocess/config wiring lands in stages 3–5.
"""

from __future__ import annotations

from gettext import gettext as _

from ...core.interfaces import (
    FilesCapability,
    ModuleContext,
    ModuleStatus,
    ServiceModule,
    StatusKind,
)
from .abraunegg import AbrauneggClient


class OneDriveModule(ServiceModule, FilesCapability):
    id = "onedrive"
    name = _("OneDrive")
    icon_name = "folder-remote-symbolic"

    def __init__(self):
        self._ctx: ModuleContext | None = None
        self._client = AbrauneggClient()

    # -- ServiceModule ----------------------------------------------------
    def activate(self, ctx: ModuleContext) -> None:
        self._ctx = ctx
        # TODO(stage 3): ensure host onedrive units exist and start --monitor.

    def deactivate(self) -> None:
        self._ctx = None
        # TODO(stage 3): stop supervised units.

    def status(self) -> ModuleStatus:
        if self._ctx is None:
            return ModuleStatus(StatusKind.UNCONFIGURED)
        return ModuleStatus(StatusKind.IDLE, detail=_("Not yet implemented"))

    # -- FilesCapability --------------------------------------------------
    def list_drives(self) -> list:
        # TODO(stage 3): enumerate via Graph /me/drives + SharePoint sites.
        return []

    def create_share_link(self, path: str, *, editable: bool = False) -> str:
        return self._client.create_share_link(path, editable=editable)
