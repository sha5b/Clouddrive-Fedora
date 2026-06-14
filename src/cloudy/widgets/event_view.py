# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Reading-pane content for a single calendar event (Outlook-style detail).

Shows the time, location, organizer and attendees, a Join/Open action bar and
RSVP buttons for meeting invites, then the event description rendered as HTML.
"""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

from .format import sender_name

_RSVP = (
    ("accept", _("Accept"), "accepted"),
    ("tentativelyAccept", _("Tentative"), "tentativelyAccepted"),
    ("decline", _("Decline"), "declined"),
)


def _open_uri(uri: str) -> None:
    if not uri:
        return
    try:
        Gio.AppInfo.launch_default_for_uri(uri, None)
    except Exception:  # noqa: BLE001
        pass


def build_event_content(event: dict, *, on_rsvp=None) -> Gtk.Widget:
    """Build the detail widget. ``on_rsvp(action)`` is called for RSVP clicks."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                     margin_top=16, margin_bottom=10, margin_start=20, margin_end=20)
    box.append(header)

    subject = Gtk.Label(label=event.get("subject") or _("(no title)"), xalign=0, wrap=True)
    subject.add_css_class("title-2")
    header.append(subject)

    when = _format_when(event.get("start", ""), event.get("end", ""), event.get("all_day"))
    if when:
        header.append(_meta_row("x-office-calendar-symbolic", when))
    if event.get("location"):
        header.append(_meta_row("mark-location-symbolic", event["location"]))
    if event.get("organizer"):
        header.append(_meta_row("contact-new-symbolic",
                                _("Organizer: %s") % sender_name(event["organizer"])))
    attendees = event.get("attendees") or []
    if attendees:
        shown = ", ".join(sender_name(a) for a in attendees[:8])
        if len(attendees) > 8:
            shown += _(" +%d more") % (len(attendees) - 8)
        header.append(_meta_row("system-users-symbolic", shown))

    # Action bar: Join / Open in calendar / RSVP.
    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=6,
                      hexpand=True)
    if event.get("online_url"):
        join = Gtk.Button(label=_("Join meeting"))
        join.add_css_class("suggested-action")
        join.connect("clicked", lambda *_a: _open_uri(event["online_url"]))
        actions.append(join)
    if event.get("web_link"):
        opn = Gtk.Button(label=_("Open in calendar"))
        opn.connect("clicked", lambda *_a: _open_uri(event["web_link"]))
        actions.append(opn)
    if actions.get_first_child() is not None:
        header.append(actions)

    if event.get("can_respond") and on_rsvp is not None:
        rsvp = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, margin_top=4)
        rsvp.add_css_class("linked")
        current = event.get("response", "none")
        for action, label, state in _RSVP:
            btn = Gtk.Button(label=label)
            if current == state:
                btn.add_css_class("suggested-action")
            btn.connect("clicked", lambda _b, a=action: on_rsvp(a))
            rsvp.append(btn)
        header.append(rsvp)

    box.append(Gtk.Separator())

    body = event.get("body", "")
    if body and body.strip():
        from .message_view import html_body_widget

        box.append(html_body_widget(body, event.get("body_html", False)))
    else:
        empty = Adw.StatusPage(icon_name="x-office-calendar-symbolic",
                               title=_("No description"))
        empty.set_vexpand(True)
        box.append(empty)
    return box


def _meta_row(icon: str, text: str) -> Gtk.Widget:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    img = Gtk.Image.new_from_icon_name(icon)
    img.add_css_class("dim-label")
    img.set_valign(Gtk.Align.START)
    row.append(img)
    label = Gtk.Label(label=text, xalign=0, wrap=True, hexpand=True)
    label.add_css_class("dim-label")
    row.append(label)
    return row


def _format_when(start: str, end: str, all_day: bool) -> str:
    if not start:
        return ""
    if "T" not in start:
        return start
    date, _sep, rest = start.partition("T")
    if all_day:
        return _("%s · All day") % date
    start_t = rest[:5]
    end_t = end.partition("T")[2][:5] if end and "T" in end else ""
    return f"{date} · {start_t}–{end_t}" if end_t else f"{date} · {start_t}"
