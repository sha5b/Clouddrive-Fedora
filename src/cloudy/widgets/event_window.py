# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Standalone event-detail window.

Opening an event (from the Calendar grid, the agenda list, or the Dashboard)
presents this **non-modal** window — the project convention for read/act
surfaces — rather than swapping an inline pane. It fetches the event off-thread,
shows the detail (time, location, organizer, the attendee response tracker, body)
with Join/Open/RSVP, and a Delete action in the header. ``on_changed`` is invoked
after a successful RSVP or delete so the opener can refresh.
"""

from __future__ import annotations

from datetime import datetime
from gettext import gettext as _

from gi.repository import Adw, Gtk

from .source_nav import run_async


def _iso_to_local_naive(iso: str):
    """Parse an ISO start/end to a naive local datetime for the editor prefill
    (the editor treats its fields as local wall-clock)."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.replace(tzinfo=None)


class EventDetailWindow(Adw.Window):
    __gtype_name__ = "CloudyEventDetailWindow"

    def __init__(self, window, account, event_id: str, *, on_changed=None):
        # NOT transient_for: an independent toplevel gets minimize/maximize
        # (GNOME hides those on transient "dialog" windows).
        super().__init__(modal=False, default_width=620, default_height=720,
                         title=_("Event"))
        self._window = window
        self._account = account
        self._eid = event_id
        self._on_changed = on_changed
        self._event: dict = {}

        self._content = Adw.Bin(vexpand=True)
        self._content.set_child(self._spinner())

        self._delete_btn = Gtk.Button(
            icon_name="user-trash-symbolic", tooltip_text=_("Delete event"),
            sensitive=False)
        self._delete_btn.connect("clicked", self._on_delete_clicked)
        self._edit_btn = Gtk.Button(
            icon_name="document-edit-symbolic", tooltip_text=_("Edit event"),
            sensitive=False)
        self._edit_btn.connect("clicked", self._on_edit_clicked)
        header = Adw.HeaderBar()
        header.set_decoration_layout(":minimize,maximize,close")
        header.pack_end(self._delete_btn)
        header.pack_end(self._edit_btn)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(self._content)
        self.set_content(toolbar)

        self._load()

    # -- load -------------------------------------------------------------
    def _load(self) -> None:
        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            return client.get_event(self._eid)

        run_async(work, self._on_loaded)

    def _on_loaded(self, event, error) -> bool:
        if error:
            self._content.set_child(Adw.StatusPage(
                icon_name="dialog-error-symbolic",
                title=_("Couldn't open event"), description=error))
            return False
        from .event_view import build_event_content

        self._event = event
        if event.get("subject"):
            self.set_title(event["subject"])
        self._content.set_child(build_event_content(event, on_rsvp=self._on_rsvp))
        editable = not str(self._eid).startswith("group:")
        self._delete_btn.set_sensitive(editable)
        self._edit_btn.set_sensitive(editable)
        return False

    # -- edit -------------------------------------------------------------
    def _on_edit_clicked(self, _btn) -> None:
        ev = self._event
        # Prefill the editor with the current values (body is left empty on
        # purpose — update_event omits an empty body, so the server's stays
        # intact; type in the body field only to replace it).
        initial = {
            "subject": ev.get("subject", ""),
            "location": ev.get("location", ""),
            "all_day": ev.get("all_day", False),
            "start_dt": _iso_to_local_naive(ev.get("start", "")),
            "end_dt": _iso_to_local_naive(ev.get("end", "")),
        }
        eid = self._eid
        account = self._account
        win = self._window

        def update(**fields):
            from .clients import build_account_client

            client = build_account_client(win.get_application(), account)
            result = client.update_event(eid, **fields)
            from gi.repository import GLib

            GLib.idle_add(self._after_edit)
            return result

        from .event_compose import EventWindow

        EventWindow(self._window, on_calendar=self._account.display_name,
                    create_fn=update, title=_("Edit event"),
                    primary_label=_("Save"), initial=initial).present()

    def _after_edit(self) -> bool:
        if self._on_changed is not None:
            self._on_changed()
        self._load()  # refresh this window's detail
        return False

    # -- actions ----------------------------------------------------------
    def _on_rsvp(self, action: str) -> None:
        self._window.add_toast(_("Sending response…"))

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            client.respond_event(self._eid, action)

        run_async(work, self._rsvp_done)

    def _rsvp_done(self, _result, error) -> bool:
        if error:
            self._window.add_toast(_("Couldn't send response: %s") % error)
            return False
        self._window.add_toast(_("Response sent."))
        if self._on_changed is not None:
            self._on_changed()
        self._load()  # refresh the detail (response state changed)
        return False

    def _on_delete_clicked(self, _btn) -> None:
        dialog = Adw.AlertDialog(
            heading=_("Delete event?"),
            body=_("This removes the event from the calendar."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response",
                       lambda _d, r: self._do_delete() if r == "delete" else None)
        dialog.present(self)

    def _do_delete(self) -> None:
        self._window.add_toast(_("Deleting…"))

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            client.delete_event(self._eid)

        run_async(work, self._deleted)

    def _deleted(self, _result, error) -> bool:
        if error:
            self._window.add_toast(_("Couldn't delete event: %s") % error)
            return False
        self._window.add_toast(_("Event deleted."))
        if self._on_changed is not None:
            self._on_changed()
        self.close()
        return False

    @staticmethod
    def _spinner() -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER,
                      valign=Gtk.Align.CENTER, hexpand=True, vexpand=True)
        sp = Gtk.Spinner(width_request=32, height_request=32)
        sp.start()
        box.append(sp)
        return box
