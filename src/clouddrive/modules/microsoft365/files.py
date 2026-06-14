# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""OneDrive / SharePoint files — the Files capability of Microsoft 365.

This is an orchestration layer, not a sync engine. Drive enumeration uses the
shared Graph client; selective sync uses the host abraunegg ``onedrive`` client;
on-demand (stages 5+) uses onedriver/rclone. See docs/MODULES.md.
"""

from __future__ import annotations

from .abraunegg import AbrauneggClient


class OneDriveFiles:
    def __init__(self, graph):
        self._graph = graph
        self._client = AbrauneggClient()

    def list_drives(self) -> list:
        # TODO(stage 3): /me/drives + SharePoint sites via the shared Graph client.
        return self._graph.list_drives()

    def create_share_link(self, path: str, *, editable: bool = False) -> str:
        # Share links come from the host client which holds the live sync state.
        return self._client.create_share_link(path, editable=editable)
