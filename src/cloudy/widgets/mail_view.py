# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Mail surface: a two-pane reader.

Left pane = a folder switcher + an email-style message list (plain ``Gtk.Label``s
so '&', '<' etc. are safe). Right pane = the selected message, rendered as real
HTML (see ``message_view``). Folders come from ``client.list_folders()``; each
folder's messages are cached independently (stale-while-revalidate).
"""

from __future__ import annotations

import threading
from gettext import gettext as _

from gi.repository import Adw, GLib, Gtk, Pango

from .format import sender_name, short_time


class MailView(Adw.Bin):
    __gtype_name__ = "CloudyMailView"

    def __init__(self, window, account):
        super().__init__()
        self._window = window
        self._account = account
        # Well-known default folder differs per provider.
        self._folder_id = "INBOX" if account.provider == "google" else "inbox"
        self._folders: list[dict] = []
        self._suppress_folder_signal = False
        self._open_mid = None
        self._messages_by_id: dict = {}
        self._rows_by_id: dict = {}

        # -- left pane: folder switcher (header) + message list ----------
        self._folder_dropdown = Gtk.DropDown(
            model=Gtk.StringList.new([_("Inbox")]), sensitive=False,
            tooltip_text=_("Choose a folder"),
        )
        self._folder_dropdown.add_css_class("flat")
        self._folder_dropdown.connect("notify::selected", self._on_folder_changed)

        sidebar_header = Adw.HeaderBar(
            show_start_title_buttons=False, show_end_title_buttons=False,
            title_widget=self._folder_dropdown,
        )

        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE,
                                 valign=Gtk.Align.START)
        self._list.add_css_class("navigation-sidebar")
        self._list.connect("row-activated", self._on_row_activated)
        list_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                         vexpand=True)
        list_scroll.set_child(self._list)

        sidebar_tb = Adw.ToolbarView()
        sidebar_tb.add_top_bar(sidebar_header)
        sidebar_tb.set_content(list_scroll)
        sidebar_page = Adw.NavigationPage(title=_("Mail"), tag="messages")
        sidebar_page.set_child(sidebar_tb)

        # -- right pane: the reading area --------------------------------
        self._reader = Adw.Bin()
        self._reader.set_child(self._reader_placeholder(
            "mail-unread-symbolic", _("No message selected"),
            _("Pick an email from the list to read it here."),
        ))
        content_header = Adw.HeaderBar(
            show_start_title_buttons=False, show_end_title_buttons=False,
        )
        self._delete_btn = Gtk.Button(
            icon_name="user-trash-symbolic", tooltip_text=_("Move to Trash"),
            sensitive=False,
        )
        self._delete_btn.connect("clicked", self._on_delete_clicked)
        content_header.pack_end(self._delete_btn)
        content_tb = Adw.ToolbarView()
        content_tb.add_top_bar(content_header)
        content_tb.set_content(self._reader)
        content_page = Adw.NavigationPage(title=_("Message"), tag="reader")
        content_page.set_child(content_tb)

        self._split = Adw.NavigationSplitView(
            min_sidebar_width=300, max_sidebar_width=460, sidebar_width_fraction=0.36,
        )
        self._split.set_sidebar(sidebar_page)
        self._split.set_content(content_page)
        self.set_child(self._split)

        self._has_data = False
        self._show_cached_or_placeholder()
        self._load_async()
        self._load_folders_async()

    # -- cache key per folder --------------------------------------------
    def _cache_key(self) -> str:
        return f"{self._account.id}:messages:{self._folder_id}"

    def _show_cached_or_placeholder(self) -> bool:
        """Render cached messages if any; return True if they were fresh."""
        self._has_data = False
        cached = self._window.get_application().cache.get(self._cache_key())
        if cached is not None:
            self._render(cached[0])  # show cached instantly
            return bool(cached[1])  # fresh enough → caller may skip the fetch
        self._set_placeholder(_("Loading mail…"))
        return False

    # -- helpers ----------------------------------------------------------
    def _clear(self) -> None:
        child = self._list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._list.remove(child)
            child = nxt

    def _set_placeholder(self, text: str) -> None:
        self._clear()
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        label = Gtk.Label(label=text, margin_top=18, margin_bottom=18)
        label.add_css_class("dim-label")
        row.set_child(label)
        self._list.append(row)

    def _reader_placeholder(self, icon: str, title: str, description: str) -> Gtk.Widget:
        return Adw.StatusPage(icon_name=icon, title=title, description=description)

    def _reader_loading(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER,
                      hexpand=True, vexpand=True)
        spinner = Gtk.Spinner(width_request=32, height_request=32)
        spinner.start()
        box.append(spinner)
        label = Gtk.Label(label=_("Opening…"))
        label.add_css_class("dim-label")
        box.append(label)
        return box

    # -- folders ----------------------------------------------------------
    def _load_folders_async(self) -> None:
        def worker():
            try:
                from .clients import build_account_client

                client = build_account_client(self._window.get_application(), self._account)
                folders = client.list_folders()
                GLib.idle_add(self._on_folders_loaded, folders)
            except Exception:  # noqa: BLE001 - folder list is non-critical
                GLib.idle_add(self._on_folders_loaded, [])

        threading.Thread(target=worker, daemon=True).start()

    def _on_folders_loaded(self, folders) -> bool:
        if not folders:
            return False
        self._folders = folders
        names = []
        selected = 0
        for i, f in enumerate(folders):
            unread = f.get("unread", 0)
            names.append(f"{f['name']} ({unread})" if unread else f["name"])
            if f["id"] == self._folder_id:
                selected = i
        self._suppress_folder_signal = True
        self._folder_dropdown.set_model(Gtk.StringList.new(names))
        self._folder_dropdown.set_selected(selected)
        self._folder_dropdown.set_sensitive(True)
        self._suppress_folder_signal = False
        return False

    def _on_folder_changed(self, dropdown, _pspec) -> None:
        if self._suppress_folder_signal:
            return
        idx = dropdown.get_selected()
        if idx < 0 or idx >= len(self._folders):
            return
        folder = self._folders[idx]
        if folder["id"] == self._folder_id:
            return
        self._folder_id = folder["id"]
        if not self._show_cached_or_placeholder():
            self._load_async()

    # -- loading ----------------------------------------------------------
    def _load_async(self) -> None:
        folder_id = self._folder_id

        def worker():
            try:
                from .clients import build_account_client

                client = build_account_client(self._window.get_application(), self._account)
                messages = client.list_messages(folder_id)
                GLib.idle_add(self._on_loaded, folder_id, messages, None)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._on_loaded, folder_id, None, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_loaded(self, folder_id, messages, error) -> bool:
        if error:
            # Never cache errors; keep any cached list on screen and only
            # surface the error if the active folder has nothing to show.
            if folder_id == self._folder_id and not self._has_data:
                self._set_placeholder(_("Couldn't load mail: %s") % error)
            return False
        self._window.get_application().cache.set(
            f"{self._account.id}:messages:{folder_id}", messages
        )
        # A late response for a folder the user already switched away from just
        # updates the cache; don't clobber the visible list.
        if folder_id == self._folder_id:
            self._render(messages)
        return False

    def _render(self, messages) -> None:
        self._messages_by_id = {}
        self._rows_by_id = {}
        if not messages:
            self._set_placeholder(_("This folder is empty."))
            self._has_data = False
            return
        self._clear()
        for msg in messages:
            row = self._mail_row(msg)
            self._list.append(row)
            self._messages_by_id[msg["id"]] = msg
            self._rows_by_id[msg["id"]] = row
        self._has_data = True

    def _refresh_row(self, mid, msg) -> None:
        """Rebuild a single row in place (e.g. after marking it read)."""
        row = self._rows_by_id.get(mid)
        if row is None:
            return
        idx = row.get_index()
        was_selected = self._list.get_selected_row() is row
        self._list.remove(row)
        new_row = self._mail_row(msg)
        self._list.insert(new_row, idx)
        self._rows_by_id[mid] = new_row
        if was_selected:
            self._list.select_row(new_row)

    # -- a single email row (plain Gtk.Labels: no markup parsing) ---------
    def _mail_row(self, msg) -> Gtk.ListBoxRow:
        unread = not msg.get("is_read", True)
        sender = sender_name(msg.get("from", "")) or _("Unknown sender")
        subject = msg.get("subject") or _("(no subject)")
        preview = (msg.get("preview") or "").replace("\n", " ").strip()

        row = Gtk.ListBoxRow(activatable=True)
        row._mid = msg["id"]

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10,
                       margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        row.set_child(hbox)

        dot = Gtk.Image.new_from_icon_name(
            "mail-unread-symbolic" if unread else "mail-read-symbolic"
        )
        dot.set_valign(Gtk.Align.CENTER)
        if not unread:
            dot.add_css_class("dim-label")
        hbox.append(dot)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        hbox.append(body)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        body.append(top)
        sender_lbl = Gtk.Label(label=sender, xalign=0, hexpand=True,
                               ellipsize=Pango.EllipsizeMode.END)
        sender_lbl.add_css_class("heading" if unread else "body")
        top.append(sender_lbl)
        time_lbl = Gtk.Label(label=short_time(msg.get("received", "")), xalign=1)
        time_lbl.add_css_class("dim-label")
        time_lbl.add_css_class("caption")
        top.append(time_lbl)

        subj_lbl = Gtk.Label(label=subject, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        if unread:
            subj_lbl.add_css_class("heading")
        body.append(subj_lbl)

        if preview:
            prev_lbl = Gtk.Label(label=preview, xalign=0, ellipsize=Pango.EllipsizeMode.END)
            prev_lbl.add_css_class("dim-label")
            prev_lbl.add_css_class("caption")
            body.append(prev_lbl)

        if msg.get("important") or msg.get("starred"):
            flags = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2,
                            valign=Gtk.Align.CENTER)
            if msg.get("important"):
                flags.append(Gtk.Image.new_from_icon_name("mail-mark-important-symbolic"))
            if msg.get("starred"):
                flags.append(Gtk.Image.new_from_icon_name("starred-symbolic"))
            hbox.append(flags)

        return row

    # -- open a message into the reading pane -----------------------------
    def _on_row_activated(self, _list, row) -> None:
        mid = getattr(row, "_mid", None)
        if mid is not None:
            self.open_message(mid)

    def open_message(self, mid) -> None:
        """Open a message in the reading pane (also used to deep-link from the
        dashboard). Selects its list row when that row is present."""
        self._open_mid = mid
        self._delete_btn.set_sensitive(True)
        self._reader.set_child(self._reader_loading())
        self._split.set_show_content(True)  # reveal the reader when collapsed

        row = self._rows_by_id.get(mid)
        if row is not None and self._list.get_selected_row() is not row:
            self._list.select_row(row)

        def worker():
            try:
                from .clients import build_account_client

                client = build_account_client(self._window.get_application(), self._account)
                full = client.get_message(mid)
                GLib.idle_add(self._show_message, mid, full, None)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._show_message, mid, None, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _show_message(self, mid, msg, error) -> bool:
        if mid != self._open_mid:
            return False  # user already opened another message
        if error:
            self._reader.set_child(self._reader_placeholder(
                "dialog-error-symbolic", _("Couldn't open message"), error,
            ))
            return False
        from .message_view import build_message_content

        self._reader.set_child(build_message_content(msg))
        self._mark_read(mid)
        return False

    # -- write-back: mark read / delete -----------------------------------
    def _mark_read(self, mid) -> None:
        cached = self._messages_by_id.get(mid)
        if cached is not None:
            if cached.get("is_read", True):
                return  # already read; no write needed
            cached["is_read"] = True  # also updates the cached list (same dict)
            self._refresh_row(mid, cached)

        def worker():
            try:
                from .clients import build_account_client

                client = build_account_client(self._window.get_application(), self._account)
                client.mark_read(mid, True)
            except Exception:  # noqa: BLE001 - best-effort (e.g. Gmail not re-consented)
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_delete_clicked(self, _btn) -> None:
        mid = self._open_mid
        if not mid:
            return
        # Optimistic: drop the row + clear the reader, then hit the server.
        row = self._rows_by_id.pop(mid, None)
        self._messages_by_id.pop(mid, None)
        if row is not None:
            self._list.remove(row)
        self._open_mid = None
        self._delete_btn.set_sensitive(False)
        self._reader.set_child(self._reader_placeholder(
            "user-trash-symbolic", _("Moved to Trash"),
            _("The message was moved to Trash."),
        ))
        self._window.add_toast(_("Moved to Trash"))

        def worker():
            try:
                from .clients import build_account_client

                client = build_account_client(self._window.get_application(), self._account)
                client.delete_message(mid)
                GLib.idle_add(self._drop_from_cache, mid)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self._delete_failed, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _drop_from_cache(self, mid) -> bool:
        cache = self._window.get_application().cache
        cached = cache.get(self._cache_key())
        if cached is not None:
            cache.set(self._cache_key(),
                      [m for m in cached[0] if m.get("id") != mid])
        return False

    def _delete_failed(self, error) -> bool:
        self._window.add_toast(_("Couldn't delete: %s") % error)
        self._load_async()  # the optimistic removal was wrong; restore from server
        return False
