# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Microsoft Graph mail/calendar/contacts module (the future-proof Exchange path).

Stage 6. EWS is retired 2027-04-01, so this targets Graph only. See docs/AUTH.md.
"""

from gettext import gettext as _

from ...core.interfaces import (
    CalendarCapability,
    MailCapability,
    ModuleContext,
    ModuleStatus,
    ServiceModule,
    StatusKind,
)


class GraphMailModule(ServiceModule, MailCapability, CalendarCapability):
    id = "graph_mail"
    name = _("Microsoft 365 Mail")
    icon_name = "mail-unread-symbolic"

    def activate(self, ctx: ModuleContext) -> None:
        self._ctx = ctx

    def deactivate(self) -> None:
        self._ctx = None

    def status(self) -> ModuleStatus:
        return ModuleStatus(StatusKind.UNCONFIGURED)

    # MailCapability / CalendarCapability — implemented in stage 6.
    def list_folders(self) -> list:
        return []

    def list_messages(self, folder_id: str, *, limit: int = 50) -> list:
        return []

    def list_calendars(self) -> list:
        return []

    def list_events(self, calendar_id: str, start, end) -> list:
        return []


MODULE = GraphMailModule
