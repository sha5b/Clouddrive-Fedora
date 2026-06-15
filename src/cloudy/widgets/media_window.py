# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Standalone image viewer — a non-modal, draggable, minimizable toplevel window
(the same convention as the compose/event editors) with a Download button.

Used to open inline chat images (and mail attachments) at full size in their own
window the user can park, resize, or minimize while doing other things.
"""

from __future__ import annotations

from gettext import gettext as _

from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk

_MAX_EDGE = 2200  # cap the decoded texture so huge images stay light to render


class ImageWindow(Adw.Window):
    """View ``data`` (image bytes) full-size; the header carries Download."""

    def __init__(self, parent, data: bytes, name: str = "image"):
        # NOT transient_for / not modal: GNOME treats transient windows as
        # dialogs and hides minimize/maximize. As an independent toplevel it can
        # be parked, resized or minimized while the main window stays usable.
        super().__init__(modal=False)
        self._parent = parent
        self._data = data
        self._name = name or "image"
        self.set_title(self._name)
        self.set_default_size(900, 700)

        save = Gtk.Button(icon_name="document-save-symbolic",
                          tooltip_text=_("Download"))
        save.connect("clicked", lambda *_a: self._save())
        header = Adw.HeaderBar()
        header.set_decoration_layout(":minimize,maximize,close")
        header.pack_end(save)

        pic = Gtk.Picture(vexpand=True, hexpand=True, can_shrink=True)
        pic.set_content_fit(Gtk.ContentFit.CONTAIN)
        try:
            pic.set_paintable(self._texture(data))
        except Exception:  # noqa: BLE001 - undecodable payload → empty viewer
            pass

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(pic)
        self.set_content(toolbar)

    @staticmethod
    def _texture(data: bytes):
        loader = GdkPixbuf.PixbufLoader()
        loader.write(data)
        loader.close()
        pix = loader.get_pixbuf()
        w, h = pix.get_width(), pix.get_height()
        scale = min(1.0, _MAX_EDGE / w, _MAX_EDGE / h)
        if scale < 1.0:
            pix = pix.scale_simple(max(1, int(w * scale)), max(1, int(h * scale)),
                                   GdkPixbuf.InterpType.BILINEAR)
        return Gdk.Texture.new_for_pixbuf(pix)

    # -- download ---------------------------------------------------------
    def _save(self) -> None:
        from .source_nav import local_initial_folder

        dialog = Gtk.FileDialog(title=_("Save"), initial_name=self._name)
        folder = local_initial_folder()
        if folder is not None:
            dialog.set_initial_folder(folder)
        dialog.save(self, None, self._on_save)

    def _on_save(self, dialog, result) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # cancelled
        if gfile is None:
            return
        try:
            gfile.replace_contents(self._data, None, False,
                                   Gio.FileCreateFlags.NONE, None)
        except GLib.Error:
            pass
