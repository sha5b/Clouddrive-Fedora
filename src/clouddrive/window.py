# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""The main application window, loaded from the Blueprint-compiled template."""

from gi.repository import Adw, Gio, Gtk

RESOURCE_PREFIX = "/com/fiberelements/Clouddrive"


@Gtk.Template(resource_path=f"{RESOURCE_PREFIX}/ui/window.ui")
class ClouddriveWindow(Adw.ApplicationWindow):
    __gtype_name__ = "ClouddriveWindow"

    split_view = Gtk.Template.Child()
    sidebar_list = Gtk.Template.Child()
    content_stack = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        app = self.get_application()
        self._settings: Gio.Settings = app.settings

        self._bind_window_state()
        self._populate_sidebar()

    def _bind_window_state(self) -> None:
        self._settings.bind(
            "window-width", self, "default-width", Gio.SettingsBindFlags.DEFAULT
        )
        self._settings.bind(
            "window-height", self, "default-height", Gio.SettingsBindFlags.DEFAULT
        )
        self._settings.bind(
            "window-maximized", self, "maximized", Gio.SettingsBindFlags.DEFAULT
        )

    def _populate_sidebar(self) -> None:
        """Seed the sidebar from discovered modules.

        Stage 0: placeholder rows. Stage 1 binds this to the account registry
        and module engine.
        """
        engine = self.get_application().engine
        for module in engine.modules():
            row = Adw.ActionRow(title=module.name, subtitle=module.id)
            icon = Gtk.Image.new_from_icon_name(module.icon_name)
            row.add_prefix(icon)
            self.sidebar_list.append(row)

    def add_toast(self, message: str) -> None:
        # A bare window has no ToastOverlay yet; print until the UI grows one.
        # TODO(stage 1): wrap content in an Adw.ToastOverlay and show here.
        print(f"[toast] {message}")
