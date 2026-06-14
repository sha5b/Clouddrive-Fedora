# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Mail surface: a two-pane reader.

Left pane = a folder switcher + an email-style message list (plain ``Gtk.Label``s
so '&', '<' etc. are safe). Right pane = the selected message, rendered as real
HTML (see ``message_view``). Folders come from ``client.list_folders()``; each
folder's messages are cached independently (stale-while-revalidate).
"""

from __future__ import annotations

import re
from gettext import gettext as _

from gi.repository import Adw, Gtk, Pango

from .format import esc, sender_name, short_time
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

_WS_RE = re.compile(r"\s+")


def _oneline(text: str) -> str:
    """Collapse every run of whitespace (incl. \\r and unicode breaks) to one
    space so list labels never wrap to multiple lines."""
    return _WS_RE.sub(" ", text or "").strip()


class MailView(Adw.Bin):
    __gtype_name__ = "CloudyMailView"

    def __init__(self, window, account):
        super().__init__()
        self._window = window
        self._account = account
        # Microsoft accounts get three sources: Me / Teams / Shared. Google only
        # has its own mailbox ("me").
        self._is_ms = account.provider == "microsoft"
        self._source = "me"
        self._folder_id = "INBOX" if account.provider == "google" else "inbox"
        self._me_folders: list[dict] = []
        self._teams: list[dict] = []          # [{id, name}] (raw group ids)
        self._shared_folders: dict = {}        # address -> [folders]
        self._suppress = False
        self._open_mid = None
        self._messages_by_id: dict = {}
        self._rows_by_id: dict = {}

        # -- left pane: source tabs + context/folder dropdowns + list ----
        self._ctx_dd = Gtk.DropDown(model=Gtk.StringList.new([]), tooltip_text=_("Choose"))
        self._ctx_dd.add_css_class("flat")
        self._ctx_dd.set_hexpand(True)
        self._ctx_dd.connect("notify::selected", self._on_ctx_changed)
        self._folder_dd = Gtk.DropDown(
            model=Gtk.StringList.new([_("Inbox")]), tooltip_text=_("Choose a folder"))
        self._folder_dd.add_css_class("flat")
        self._folder_dd.set_hexpand(True)
        self._folder_dd.connect("notify::selected", self._on_folder_changed)
        self._add_shared_btn = Gtk.Button(
            icon_name="list-add-symbolic", tooltip_text=_("Add a shared mailbox"))
        self._add_shared_btn.add_css_class("flat")
        self._add_shared_btn.connect("clicked", self._on_add_shared)
        self._star_btn = Gtk.Button(
            icon_name="non-starred-symbolic",
            tooltip_text=_("Pin this mailbox to the Dashboard"))
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

        compose_btn = Gtk.Button(
            icon_name="mail-message-new-symbolic", tooltip_text=_("New message"))
        compose_btn.connect("clicked", self._on_compose_clicked)

        sidebar_tb = Adw.ToolbarView()
        if self._is_ms:
            tabs = SourceTabs(self._on_source_changed)
            header = Adw.HeaderBar(
                show_start_title_buttons=False, show_end_title_buttons=False,
                title_widget=tabs)
            header.pack_start(compose_btn)
            sidebar_tb.add_top_bar(header)
            bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                          margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
            bar.append(self._ctx_dd)
            bar.append(self._folder_dd)
            bar.append(self._star_btn)
            bar.append(self._add_shared_btn)
            sidebar_tb.add_top_bar(bar)
        else:
            header = Adw.HeaderBar(
                show_start_title_buttons=False, show_end_title_buttons=False,
                title_widget=self._folder_dd)
            header.pack_start(compose_btn)
            sidebar_tb.add_top_bar(header)
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
        self._reply_btn = Gtk.Button(
            icon_name="mail-reply-sender-symbolic", tooltip_text=_("Reply"),
            sensitive=False,
        )
        self._reply_btn.connect("clicked", self._on_reply_clicked)
        content_header.pack_start(self._reply_btn)
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

        self._ctx_items: list = []
        self._folder_items: list = []
        self._has_data = False
        self._update_source_ui()
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
        clear_listbox(self._list)

    def _set_placeholder(self, text: str) -> None:
        self._clear()
        self._list.append(message_row(text))

    def _reauth_prompt(self) -> None:
        """Show the re-sign-in call-to-action (token lacks the shared scope)."""
        self._clear()
        self._list.append(action_row(
            SCOPE_HINT, _("Re-sign in"),
            lambda: self._window.sign_in_account(self._account)))

    def _reader_placeholder(self, icon: str, title: str, description: str) -> Gtk.Widget:
        # StatusPage parses title/description as Pango markup; escape since one
        # caller passes a raw API error string (may contain < or &).
        return Adw.StatusPage(icon_name=icon, title=esc(title),
                              description=esc(description))

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

    # -- sources (Me / Teams / Shared) -----------------------------------
    def _shared_addresses(self) -> list:
        return list(self._account.shared_mailboxes or [])

    @staticmethod
    def _label(f) -> str:
        unread = f.get("unread", 0)
        return f"{f['name']} ({unread})" if unread else f["name"]

    def _load_folders_async(self) -> None:
        """Load the Me folders and (for Microsoft) the Teams list up front."""
        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            try:
                folders = client.list_folders()
            except Exception:  # noqa: BLE001
                folders = []
            teams = []
            if self._is_ms and hasattr(client, "list_groups"):
                try:
                    teams = client.list_groups()
                except Exception:  # noqa: BLE001 - needs Group.Read.All consent
                    teams = []
            return folders, teams

        # On a hard failure (e.g. no client) fall back to empty sources.
        run_async(work, lambda res, _error: self._on_sources_loaded(*(res or ([], []))))

    def _on_sources_loaded(self, folders, teams) -> bool:
        self._me_folders = folders
        self._teams = teams
        # If we're showing the source the data belongs to, refresh its dropdowns.
        if self._source == "me":
            self._populate_folders(self._me_folders, initial=True)
        elif self._source == "teams":
            self._populate_context()
        return False

    def _update_source_ui(self) -> None:
        """Show the right dropdowns/buttons for the active source."""
        if not self._is_ms:
            return
        self._ctx_dd.set_visible(self._source in ("teams", "shared"))
        self._folder_dd.set_visible(self._source in ("me", "shared"))
        self._add_shared_btn.set_visible(self._source == "shared")
        if self._source == "me":
            self._ctx_current = None
        self._update_star()

    def _on_source_changed(self, source) -> None:
        if source == self._source:
            return
        self._source = source
        self._update_source_ui()
        if source == "me":
            self._populate_folders(self._me_folders)
        else:
            self._populate_context()

    def _populate_context(self) -> None:
        """Fill the context dropdown (teams list or shared-mailbox list)."""
        if self._source == "teams":
            items = [{"id": t["id"], "name": t["name"]} for t in self._teams]
            empty = _("No group mailboxes.")
        else:
            items = [{"id": a, "name": a} for a in self._shared_addresses()]
            empty = _("Add a shared mailbox with +.")
        self._ctx_items = items
        self._suppress = True
        self._ctx_dd.set_model(Gtk.StringList.new([i["name"] for i in items] or [_("None")]))
        self._ctx_dd.set_sensitive(bool(items))
        self._ctx_dd.set_selected(0)
        self._suppress = False
        if not items:
            self._folder_dd.set_visible(False)
            self._set_placeholder(empty)
            return
        self._on_ctx_changed(self._ctx_dd, None)

    def _on_ctx_changed(self, dropdown, _pspec) -> None:
        if self._suppress:
            return
        idx = dropdown.get_selected()
        items = getattr(self, "_ctx_items", [])
        if not (0 <= idx < len(items)):
            return
        self._ctx_current = items[idx]
        self._update_star()
        if self._source == "teams":
            self._select_folder(f"group:{items[idx]['id']}")
        else:  # shared: load that mailbox's folders into the folder dropdown
            self._load_shared_folders(items[idx]["id"])

    # -- pin (star) the current team/shared mailbox ----------------------
    def _update_star(self) -> None:
        active = self._source in ("teams", "shared") and self._ctx_current is not None
        self._star_btn.set_visible(active)
        if not active:
            return
        pinned = is_pinned(self._account, "mail", self._source, self._ctx_current["id"])
        self._star_btn.set_icon_name("starred-symbolic" if pinned else "non-starred-symbolic")

    def _on_star_clicked(self, _btn) -> None:
        if self._ctx_current is None:
            return
        toggle_pin(self._window, self._account, kind="mail", source=self._source,
                   sid=self._ctx_current["id"], name=self._ctx_current["name"])
        self._update_star()

    def _populate_folders(self, folders, *, initial: bool = False) -> None:
        self._folder_items = folders
        self._suppress = True
        self._folder_dd.set_model(
            Gtk.StringList.new([self._label(f) for f in folders] or [_("None")]))
        self._folder_dd.set_sensitive(bool(folders))
        idx = next((i for i, f in enumerate(folders) if f["id"] == self._folder_id), 0)
        self._folder_dd.set_selected(idx)
        self._suppress = False
        if not folders:
            self._set_placeholder(_("No folders."))
            return
        fid = folders[idx]["id"]
        if not (initial and fid == self._folder_id):
            self._select_folder(fid)

    def _on_folder_changed(self, dropdown, _pspec) -> None:
        if self._suppress:
            return
        folders = getattr(self, "_folder_items", [])
        idx = dropdown.get_selected()
        if 0 <= idx < len(folders) and folders[idx]["id"] != self._folder_id:
            self._select_folder(folders[idx]["id"])

    def _load_shared_folders(self, address) -> None:
        cached = self._shared_folders.get(address)
        if cached is not None:
            self._populate_folders(cached)
            return
        self._set_placeholder(_("Loading folders…"))

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            return client.list_shared_folders(address)

        run_async(work, lambda folders, error: self._on_shared_folders(address, folders, error))

    def _on_shared_folders(self, address, folders, error) -> bool:
        if is_scope_error(error):
            self._reauth_prompt()
            self._folder_dd.set_sensitive(False)
            return False
        if error or not folders:
            self._set_placeholder(
                _("Couldn't open %(addr)s: %(err)s") % {"addr": address, "err": error}
                if error else _("No folders in %s.") % address
            )
            self._folder_dd.set_sensitive(False)
            return False
        self._shared_folders[address] = folders
        if self._source == "shared":
            self._populate_folders(folders)
        return False

    def _on_add_shared(self, _btn) -> None:
        present_add_shared_dialog(
            self._window, self._account, lambda _addr: self._populate_context())

    def _select_folder(self, fid) -> None:
        self._folder_id = fid
        if not self._show_cached_or_placeholder():
            self._load_async()

    # -- loading ----------------------------------------------------------
    def _load_async(self) -> None:
        folder_id = self._folder_id

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            return client.list_messages(folder_id)

        run_async(work, lambda messages, error: self._on_loaded(folder_id, messages, error))

    def _on_loaded(self, folder_id, messages, error) -> bool:
        if error:
            # Never cache errors; keep any cached list on screen and only
            # surface the error if the active folder has nothing to show.
            if folder_id == self._folder_id and not self._has_data:
                if is_scope_error(error):
                    self._reauth_prompt()
                else:
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
        sender = _oneline(sender_name(msg.get("from", ""))) or _("Unknown sender")
        subject = _oneline(msg.get("subject", "")) or _("(no subject)")
        preview = _oneline(msg.get("preview", ""))

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
        # Group conversations are read-only (no per-user delete).
        self._delete_btn.set_sensitive(not str(mid).startswith("group:"))
        self._reply_btn.set_sensitive(False)  # enabled once the body loads
        self._reader.set_child(self._reader_loading())
        self._split.set_show_content(True)  # reveal the reader when collapsed

        row = self._rows_by_id.get(mid)
        if row is not None and self._list.get_selected_row() is not row:
            self._list.select_row(row)

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            return client.get_message(mid)

        run_async(work, lambda full, error: self._show_message(mid, full, error))

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
        self._open_msg = msg
        self._reply_btn.set_sensitive(True)
        self._mark_read(mid)
        return False

    # -- compose / reply --------------------------------------------------
    def _send_context(self):
        """Return ``(source, address)`` for sending as the active mailbox.

        Shared mailboxes have their own address (send-as); Me and Teams/group
        sources fall back to the signed-in user for new messages."""
        if self._source == "shared" and self._ctx_current is not None:
            return "shared", self._ctx_current["id"]
        return "me", None

    def _from_label(self) -> str:
        source, address = self._send_context()
        if source == "shared" and address:
            return address
        return self._account.display_name

    def _on_compose_clicked(self, _btn) -> None:
        from .compose_view import ComposeWindow

        source, address = self._send_context()

        def send(to, subject, body):
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            client.send_mail(to=to, subject=subject, body=body,
                             source=source, address=address)

        ComposeWindow(self._window, self._account, from_label=self._from_label(),
                      send_fn=send).present()

    def _on_reply_clicked(self, _btn) -> None:
        mid = self._open_mid
        if not mid:
            return
        from .compose_view import ComposeWindow

        meta = getattr(self, "_open_msg", None) or self._messages_by_id.get(mid, {})
        subject = meta.get("subject", "")
        if subject and not subject.lower().startswith("re:"):
            subject = _("Re: %s") % subject

        def send(_to, _subject, body):
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            client.reply_mail(mid, body)

        ComposeWindow(
            self._window, self._account, from_label=self._account.display_name,
            send_fn=send, to=meta.get("from", ""), subject=subject, title=_("Reply"),
        ).present()

    # -- write-back: mark read / delete -----------------------------------
    def _mark_read(self, mid) -> None:
        cached = self._messages_by_id.get(mid)
        if cached is not None:
            if cached.get("is_read", True):
                return  # already read; no write needed
            cached["is_read"] = True  # also updates the cached list (same dict)
            self._refresh_row(mid, cached)

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            client.mark_read(mid, True)

        # Best-effort (e.g. Gmail not re-consented): ignore the outcome.
        run_async(work, lambda _r, _e: False)

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

        def work():
            from .clients import build_account_client

            client = build_account_client(self._window.get_application(), self._account)
            client.delete_message(mid)

        run_async(work, lambda _r, error:
                  self._delete_failed(error) if error else self._drop_from_cache(mid))

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
