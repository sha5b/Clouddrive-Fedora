# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Inline read view for a single mail message (pushed into the content nav).

Bodies are shown as plain text. If only HTML is available we strip tags rather
than pull in WebKitGTK; rich rendering can come later.
"""

from __future__ import annotations

import html
import re
from gettext import gettext as _

from gi.repository import Adw, Gtk

from .format import esc, sender_name, short_time

_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(script|style|head)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_BLOCK_RE = re.compile(r"</(p|div|tr|table|h[1-6]|li|ul|ol|blockquote)>", re.IGNORECASE)


def _to_text(body: str) -> str:
    """Convert an HTML or plain body to tidy, readable plain text."""
    if "<" in body and ">" in body:
        body = _STYLE_RE.sub("", body)
        body = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
        body = _BLOCK_RE.sub("\n", body)
        body = _TAG_RE.sub("", body)
        body = html.unescape(body)

    # Tidy whitespace: trim each line, drop trailing spaces, collapse runs of
    # blank lines, and remove the leading indentation email HTML loves to emit.
    lines = [ln.strip() for ln in body.replace("\r", "").split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_message_page(msg: dict) -> Adw.NavigationPage:
    """Build a NavigationPage for one message (back button via NavigationView)."""
    toolbar = Adw.ToolbarView()
    toolbar.add_top_bar(Adw.HeaderBar())

    scrolled = Gtk.ScrolledWindow(
        hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True
    )
    toolbar.set_content(scrolled)

    clamp = Adw.Clamp(maximum_size=720, margin_top=18, margin_bottom=24,
                      margin_start=18, margin_end=18)
    scrolled.set_child(clamp)

    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    clamp.set_child(box)

    subject = Gtk.Label(label=msg.get("subject") or _("(no subject)"), xalign=0, wrap=True)
    subject.add_css_class("title-2")
    box.append(subject)

    meta_parts = []
    if msg.get("from"):
        meta_parts.append(_("From: %s") % sender_name(msg["from"]))
    if msg.get("to"):
        meta_parts.append(_("To: %s") % msg["to"])
    if msg.get("received"):
        meta_parts.append(short_time(msg["received"]))
    if meta_parts:
        meta = Gtk.Label(label=" · ".join(meta_parts), xalign=0, wrap=True,
                         margin_bottom=12)
        meta.add_css_class("dim-label")
        meta.add_css_class("caption")
        box.append(meta)

    # Body as a wrapping, selectable label (no internal scroller -> the page
    # scrolls naturally; no giant empty TextView).
    body = Gtk.Label(label=_to_text(msg.get("body", "")) or _("(empty message)"),
                     xalign=0, yalign=0, wrap=True, selectable=True)
    body.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    body.add_css_class("body")
    box.append(body)

    title = esc((msg.get("subject") or _("Message"))[:40])
    page = Adw.NavigationPage(title=title, tag="message")
    page.set_child(toolbar)
    return page
