# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Calendar surface: a two-pane week agenda (Outlook-style).

Left pane = events for the next 7 days, grouped by day. For Microsoft accounts a
Me / Teams / Shared switcher mirrors the Mail view: **Me** is your own calendar,
**Teams** picks a M365 group/team calendar, **Shared** picks another mailbox's
calendar you have delegated access to. Right pane = the selected event's detail,
with Join/Open and RSVP actions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk, Pango

from .source_nav import (
    SCOPE_HINT,
    SourceTabs,
    action_row,
    clear_listbox,
    is_pinned,
    is_scope_error,
    message_row,
    present_add_shared_dialog,
    run_async,
    toggle_pin,
)


class CalendarView(Adw.Bin):
    __gtype_name__ = "CloudyCalendarView"

    def __init__(self, window, account):
        super().__init__()
        self._window = window
        self._account = account
        self._is_ms = account.provider == "microsoft"
        self._source = "me"
        self._context = None        # group id (teams) or address (shared)
        self._groups = None         # lazily loaded list[{id, name}]
        self._ctx_items: list = []
        self._suppress = False
        self._open_eid = None
        self._events: list = []
        self._has_data = False

        # -- left pane: source switcher + agenda list --------------------
        self._ctx_dd = Gtk.DropDown(model=Gtk.StringList.new([]), tooltip_text=_("Choose"))
        self._ctx_dd.add_css_class("flat")
        self._ctx_dd.set_hexpand(True)
        self._ctx_dd.connect("notify::selected", self._on_ctx_changed)
        self._add_shared_btn = Gtk.Button(
            icon_name="list-add-symbolic", tooltip_text=_("Add a shared mailbox"))
        self._add_shared_btn.add_css_class("flat")
        self._add_shared_btn.connect("clicked", self._on_add_shared)
        self._star_btn = Gtk.Button(
            icon_name="non-starred-symbolic",
            tooltip_text=_("Pin this calendar to the Dashboard"))
        self._star_btn.add_css_class("flat")
        self._star_btn.connect("clicked", self._on_star_clicked)
        self._ctx_current = None  # {"id", "name"} of the selected team/shared source

        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE,
                                 valign=Gtk.Align.START)
        self._list.add_css_class("navigation-sidebar")
        self._list.connect("row-activated", self._on_row_activated)
        list_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                         vexpand=True)
        list_scroll.set_child(self._list)

        new_btn = Gtk.Button(
            icon_name="appointment-new-symbolic", tooltip_text=_("New event"))
        new_btn.connect("clicked", self._on_new_event_clicked)

        sidebar_tb = Adw.ToolbarView()
        if self._is_ms:
            header = Adw.HeaderBar(
                show_start_title_buttons=False, show_end_title_buttons=False,
                title_widget=SourceTabs(self._on_source_changed))
            header.pack_start(new_btn)
            sidebar_tb.add_top_bar(header)
            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                          margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
            range_lbl = Gtk.Label(label=_("Next 7 days"), xalign=0, hexpand=True)
            range_lbl.add_css_class("dim-label")
            bar.append(range_lbl)
            bar.append(self._ctx_dd)
            bar.append(self._star_btn)
            bar.append(self._add_shared_btn)
            sidebar_tb.add_top_bar(bar)
        else:
            header = Adw.HeaderBar(
                show_start_title_buttons=False, show_end_title_buttons=False,
                title_widget=Gtk.Label(label=_("Next 7 days")))
            header.pack_start(new_btn)
            sidebar_tb.add_top_bar(header)
        sidebar_tb.set_content(list_scroll)
        sidebar_page = Adw.NavigationPage(title=_("Calendar"), tag="agenda")
        sidebar_page.set_child(sidebar_tb)

        # -- right pane: event detail ------------------------------------
        self._reader = Adw.Bin()
        self._reader.set_child(Adw.StatusPage(
            icon_name="x-office-calendar-symbolic", title=_("No event selected"),
            description=_("Pick an event to see its details here."),
        ))
        content_header = Adw.HeaderBar(show_start_title_buttons=False,
                                       show_end_title_buttons=False)
        self._delete_btn = Gtk.Button(
            icon_name="user-trash-symbolic", tooltip_text=_("Delete event"),
            sensitive=False)
        self._delete_btn.connect("clicked", self._on_delete_event_clicked)
        content_header.pack_end(self._delete_btn)
        content_tb = Adw.ToolbarView()
        content_tb.add_top_bar(content_header)
        content_tb.set_content(self._reader)
        content_page = Adw.NavigationPage(title=_("Event"), tag="event")
        content_page.set_child(content_tb)

        self._split = Adw.NavigationSplitView(
            min_sidebar_width=320, max_sidebar_width=480, sidebar_width_fraction=0.4,
        )
        self._split.set_sidebar(sidebar_page)
        self._split.set_content(content_page)
        self.set_child(self._split)

        self._update_source_ui()
        self._select_context(None)  # load "Me" from cache or the server

    # -- cache + agenda list ---------------------------------------------
    def _cache_key(self) -> str:
        if self._source == "teams" and self._context:
            return f"{self._account.id}:events:group:{self._context}:7d"
        if self._source == "shared" and self._context:
            return f"{self._account.id}:events:shared:{self._context}:7d"
        return f"{self._account.id}:events:me:7d"

    def _clear(self) -> None:
        clear_listbox(self._list)

    def _set_message(self, text: str) -> None:
        self._clear()
        self._list.append(message_row(text))

    def _render(self, events) -> None:
        self._events = events
        self._clear()
        if not events:
            self._set_message(_("No events in the next 7 days."))
            self._has_data = False
            return
        last_day = None
        for ev in events:
            day = (ev.get("start", "") or "").partition("T")[0]
            if day != last_day:
                self._list.append(self._day_header(day))
                last_day = day
            self._list.append(self._event_row(ev))
        self._has_data = True

    def _day_header(self, day: str) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        label = Gtk.Label(label=_pretty_day(day), xalign=0,
                          margin_top=10, margin_bottom=2, margin_start=12)
        label.add_css_class("heading")
        label.add_css_class("dim-label")
        row.set_child(label)
        return row

    def _event_row(self, ev) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow(activatable=True)
        row._eid = ev.get("id")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12,
                      margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        row.set_child(box)

        time_lbl = Gtk.Label(label=_time_label(ev), xalign=0, width_chars=11)
        time_lbl.add_css_class("caption")
        time_lbl.add_css_class("dim-label")
        time_lbl.set_valign(Gtk.Align.START)
        box.append(time_lbl)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        box.append(text)
        title = Gtk.Label(label=ev.get("subject") or _("(no title)"), xalign=0,
                          ellipsize=Pango.EllipsizeMode.END)
        title.add_css_class("body")
        text.append(title)
        if ev.get("location"):
            sub = Gtk.Label(label=ev["location"], xalign=0,
                            ellipsize=Pango.EllipsizeMode.END)
            sub.add_css_class("caption")
            sub.add_css_class("dim-label")
            text.append(sub)
        return row

    # -- sources (Me / Teams / Shared) -----------------------------------
    def _shared_addresses(self) -> list:
        return list(self._account.shared_mailboxes or [])

    def _update_source_ui(self) -> None:
        if not self._is_ms:
            return
        self._ctx_dd.set_visible(self._source in ("teams", "shared"))
        self._add_shared_btn.set_visible(self._source == "shared")
        if self._source == "me":
            self._ctx_current = None
        self._update_star()

    def _update_star(self) -> None:
        active = self._source in ("teams", "shared") and self._ctx_current is not None
        self._star_btn.set_visible(active)
        if not active:
            return
        pinned = is_pinned(self._account, "calendar", self._source, self._ctx_current["id"])
        self._star_btn.set_icon_name("starred-symbolic" if pinned else "non-starred-symbolic")

    def _on_star_clicked(self, _btn) -> None:
        if self._ctx_current is None:
            return
        toggle_pin(self._window, self._account, kind="calendar", source=self._source,
                   sid=self._ctx_current["id"], name=self._ctx_current["name"])
        self._update_star()

    def _on_source_changed(self, source) -> None:
        if source == self._source:
            return
        self._source = source
        self._update_source_ui()
        if source == "me":
            self._select_context(None)
        else:
            self._populate_context()

    def _populate_context(self) -> None:
        """Fill the context dropdown (teams list or shared-mailbox list)."""
        if self._source == "teams":
            if self._groups is None:  # first visit: fetch the group list
                self._set_message(_("Loading teams…"))
                self._load_groups_async()
                return
            items = [{"id": g["id"], "name": g["name"]} for g in self._groups]
            empty = _("No team calendars.")
        else:  # shared
            items = [{"id": a, "name": a} for a in self._shared_addresses()]
            empty = _("Add a shared mailbox with +.")
        self._ctx_items = items
        self._suppress = True
        self._ctx_dd.set_model(Gtk.StringList.new([i["name"] for i in items] or [_("None")]))
        self._ctx_dd.set_sensitive(bool(items))
        self._ctx_dd.set_selected(0)
        self._suppress = False
        if not items:
            self._ctx_current = None
            self._update_star()
            self._set_message(empty)
            return
        self._ctx_current = items[0]
        self._update_star()
        self._select_context(items[0]["id"])

    def _on_ctx_changed(self, dropdown, _pspec) -> None:
        if self._suppress:
            return
        idx = dropdown.get_selected()
        if 0 <= idx < len(self._ctx_items):
            self._ctx_current = self._ctx_items[idx]
            self._update_star()
            self._select_context(self._ctx_items[idx]["id"])

    def _on_add_shared(self, _btn) -> None:
        present_add_shared_dialog(
            self._window, self._account, lambda _addr: self._populate_context())

    def _load_groups_async(self) -> None:
        from .graph_helper import build_graph_client

        run_async(
            lambda: build_graph_client(
                self._window.get_application(), self._account).list_groups(),
            self._on_groups_loaded,
        )

    def _on_groups_loaded(self, groups, error) -> bool:
        if error is not None:
            self._groups = []
            if is_scope_error(error) or "Group.Read" in error:
                self._reauth_prompt()
            else:
                self._set_message(_("Couldn't load teams: %s") % error)
            return False
        self._groups = groups
        if self._source == "teams":
            self._populate_context()
        return False

    def _reauth_prompt(self) -> None:
        self._clear()
        self._list.append(action_row(
            SCOPE_HINT, _("Re-sign in"),
            lambda: self._window.sign_in_account(self._account)))

    # -- loading events ---------------------------------------------------
    def _select_context(self, context) -> None:
        """Switch to a calendar source, showing cached events if fresh enough."""
        self._context = context
        self._has_data = False
        cached = self._window.get_application().cache.get(self._cache_key())
        if cached is not None:
            self._render(cached[0])
            if cached[1]:
                return  # fresh; skip the fetch
        else:
            self._set_message(_("Loading calendar…"))
        self._load_async()

    def _load_async(self) -> None:
        now = datetime.now(timezone.utc)
        start_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_iso = (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        source, context, key = self._source, self._context, self._cache_key()

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            if source == "teams" and context:
                return client.list_group_events(context, start_iso, end_iso)
            if source == "shared" and context:
                return client.list_shared_events(context, start_iso, end_iso)
            return client.list_events(start_iso, end_iso)

        run_async(work, lambda events, error: self._on_loaded(key, events, error))

    def _on_loaded(self, key, events, error) -> bool:
        # Cache successful loads even if the user already switched away.
        if not error and events is not None:
            self._window.get_application().cache.set(key, events)
            # Mirror your own calendar into the GNOME Shell calendar (EDS),
            # best-effort and off-thread (no-op unless the setting is on).
            if key == f"{self._account.id}:events:me:7d" and events:
                self._publish_to_eds(events)
        if key != self._cache_key():
            return False  # a stale response for a source we left
        if error:
            if not self._has_data:
                if is_scope_error(error):
                    self._reauth_prompt()
                else:
                    self._set_message(_("Couldn't load calendar: %s") % error)
            return False
        self._render(events)
        return False

    # -- event detail -----------------------------------------------------
    def _on_row_activated(self, _list, row) -> None:
        eid = getattr(row, "_eid", None)
        if eid is None:
            return
        self._open_eid = eid
        self._delete_btn.set_sensitive(False)  # enabled once detail loads
        self._reader.set_child(self._spinner())
        self._split.set_show_content(True)

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            return client.get_event(eid)

        run_async(work, lambda event, error: self._show_event(eid, event, error))

    def _show_event(self, eid, event, error) -> bool:
        if eid != self._open_eid:
            return False
        if error:
            self._reader.set_child(Adw.StatusPage(
                icon_name="dialog-error-symbolic",
                title=_("Couldn't open event"), description=error))
            return False
        from .event_view import build_event_content

        self._reader.set_child(build_event_content(event, on_rsvp=self._make_rsvp(eid)))
        self._delete_btn.set_sensitive(self._event_deletable(eid))
        return False

    # -- create / delete --------------------------------------------------
    def _create_context(self):
        """Return ``(source, address)`` for the calendar to write to."""
        if self._is_ms and self._source == "shared" and self._ctx_current is not None:
            return "shared", self._ctx_current["id"]
        return "me", None

    def _event_deletable(self, eid) -> bool:
        """Group/team events are read-only; everything else can be deleted."""
        return not str(eid).startswith("group:")

    def _on_new_event_clicked(self, _btn) -> None:
        if self._is_ms and self._source == "teams":
            self._window.add_toast(
                _("Team calendars are read-only here. Switch to Me or Shared."))
            return
        source, address = self._create_context()
        on_calendar = address if (source == "shared" and address) \
            else self._account.display_name

        def create(**fields):
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            result = client.create_event(source=source, address=address, **fields)
            GLib.idle_add(self._reload_current)
            return result

        from .event_compose import EventWindow

        EventWindow(self._window, on_calendar=on_calendar,
                    create_fn=create).present()

    def _reload_current(self) -> bool:
        """Force a re-fetch of the active source after a write."""
        self._has_data = False
        self._load_async()
        return False

    def _on_delete_event_clicked(self, _btn) -> None:
        eid = self._open_eid
        if not eid:
            return
        dialog = Adw.AlertDialog(
            heading=_("Delete event?"),
            body=_("This removes the event from the calendar."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("delete", _("Delete"))
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect(
            "response",
            lambda _d, r: self._do_delete_event(eid) if r == "delete" else None)
        dialog.present(self._window)

    def _do_delete_event(self, eid) -> None:
        self._window.add_toast(_("Deleting…"))

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            client.delete_event(eid)

        run_async(work, lambda _r, error: self._event_deleted(eid, error))

    def _event_deleted(self, eid, error) -> bool:
        if error:
            self._window.add_toast(_("Couldn't delete event: %s") % error)
            return False
        self._window.add_toast(_("Event deleted."))
        row = self._row_for(eid)
        if row is not None:
            self._list.remove(row)
        self._events = [e for e in self._events if e.get("id") != eid]
        if eid == self._open_eid:
            self._open_eid = None
            self._delete_btn.set_sensitive(False)
            self._reader.set_child(Adw.StatusPage(
                icon_name="x-office-calendar-symbolic", title=_("Event deleted")))
        self._reload_current()  # refresh counts/cache from the server
        return False

    def _make_rsvp(self, eid):
        def on_rsvp(action):
            self._window.add_toast(_("Sending response…"))

            def work():
                from .clients import build_account_client

                client = build_account_client(self._window.get_application(), self._account)
                client.respond_event(eid, action)

            run_async(work, lambda _r, error: self._rsvp_done(eid, error))
        return on_rsvp

    def _rsvp_done(self, eid, error) -> bool:
        if error:
            self._window.add_toast(_("Couldn't send response: %s") % error)
        else:
            self._window.add_toast(_("Response sent."))
            if eid == self._open_eid:
                self._on_row_activated(self._list, self._row_for(eid) or self._list)
        return False

    def _row_for(self, eid):
        row = self._list.get_first_child()
        while row is not None:
            if getattr(row, "_eid", None) == eid:
                return row
            row = row.get_next_sibling()
        return None

    def _publish_to_eds(self, events) -> None:
        import threading

        app = self._window.get_application()
        account = self._account

        def work():
            try:
                from ..core.eds_publish import publish_events

                publish_events(app, account, events)
            except Exception:  # noqa: BLE001 - EDS mirroring never affects the UI
                pass

        threading.Thread(target=work, daemon=True).start()

    def _spinner(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER,
                      valign=Gtk.Align.CENTER, hexpand=True, vexpand=True)
        spinner = Gtk.Spinner(width_request=32, height_request=32)
        spinner.start()
        box.append(spinner)
        return box


def _time_label(ev) -> str:
    start = ev.get("start", "")
    if ev.get("all_day"):
        return _("All day")
    if "T" in start:
        return start.partition("T")[2][:5]
    return ""


def _pretty_day(day: str) -> str:
    try:
        d = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        return day
    today = datetime.now().date()
    if d == today:
        return _("Today · %s") % day
    if d == today + timedelta(days=1):
        return _("Tomorrow · %s") % day
    return day
