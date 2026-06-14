# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Shared base for editor surfaces (compose, new event, …).

The convention for Cloudy: anything you *edit and submit* opens as a **non-modal
window**, not a modal dialog — so you can keep reading/copying from the main
window (and other emails) while you write. This base provides the standard
chrome: a header with Cancel + a primary action button, an in-window toast
overlay, and a content area the subclass fills.

Subclasses set the body with :meth:`set_body` and implement :meth:`on_primary`.
"""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, Gtk


class EditorWindow(Adw.Window):
    def __init__(self, parent, *, title: str, primary_label: str,
                 default_width: int = 640, default_height: int = 600):
        super().__init__(transient_for=parent, modal=False)
        self.set_title(title)
        self.set_default_size(default_width, default_height)

        self.primary_btn = Gtk.Button(label=primary_label)
        self.primary_btn.add_css_class("suggested-action")
        self.primary_btn.connect("clicked", lambda *_a: self.on_primary())
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_a: self.close())

        header = Adw.HeaderBar()
        header.pack_start(cancel)
        header.pack_end(self.primary_btn)

        self._toolbar = Adw.ToolbarView()
        self._toolbar.add_top_bar(header)
        self._toast = Adw.ToastOverlay(child=self._toolbar)
        self.set_content(self._toast)

    # -- API for subclasses ----------------------------------------------
    def set_body(self, widget: Gtk.Widget) -> None:
        self._toolbar.set_content(widget)

    def toast(self, message: str) -> None:
        self._toast.add_toast(Adw.Toast(title=message))

    def on_primary(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
