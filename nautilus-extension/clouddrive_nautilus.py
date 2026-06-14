# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Clouddrive Nautilus extension (host-side, nautilus-python API 4.0 / GTK4).

This runs in the HOST Nautilus process (not in the Flatpak sandbox). It talks to
the Clouddrive app over D-Bus (see clouddrive.core.dbus_service) to:
  * add right-click controls (Sync this folder / Free up space / Copy share link),
  * draw per-file sync-status emblems.

Install to ~/.local/share/nautilus-python/extensions/ and run `nautilus -q`.
Requires the python3-nautilus (4.x) bindings.

Note on the 4.0 API: MenuProvider.get_file_items(files) no longer takes a window
argument, and PropertyPageProvider was replaced by PropertiesModelProvider.

Stage 0: scaffold with the provider structure; the D-Bus calls are TODOs filled
in alongside core.dbus_service (stage 4).
"""

import gi

gi.require_version("Nautilus", "4.0")
from gi.repository import GObject, Nautilus  # noqa: E402

BUS_NAME = "com.fiberelements.Clouddrive"
OBJECT_PATH = "/com/fiberelements/Clouddrive/Sync"
INTERFACE = "com.fiberelements.Clouddrive.Sync"


class ClouddriveMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    """Right-click controls for files/folders Clouddrive manages."""

    def get_file_items(self, files):  # API 4.0: no window arg
        if not files:
            return []
        # TODO(stage 4): only show for paths under a managed root (query D-Bus).
        copy_link = Nautilus.MenuItem(
            name="Clouddrive::copy_share_link",
            label="Copy OneDrive Share Link",
            tip="Create and copy a sharing link via Clouddrive",
        )
        copy_link.connect("activate", self._on_copy_link, files)

        free_space = Nautilus.MenuItem(
            name="Clouddrive::free_up_space",
            label="Free Up Space",
            tip="Remove the local copy; keep the file online",
        )
        free_space.connect("activate", self._on_free_space, files)
        return [copy_link, free_space]

    def get_background_items(self, folder):
        sync = Nautilus.MenuItem(
            name="Clouddrive::sync_folder",
            label="Sync This Folder with Clouddrive",
            tip="Mark this folder for synchronization",
        )
        sync.connect("activate", self._on_sync_folder, folder)
        return [sync]

    # -- handlers (stage 4: call the D-Bus methods) -----------------------
    def _on_copy_link(self, _menu, files):
        pass  # TODO(stage 4): Sync.CreateShareLink(path, editable=False)

    def _on_free_space(self, _menu, files):
        pass  # TODO(stage 4): Sync.FreeUpSpace(path)

    def _on_sync_folder(self, _menu, folder):
        pass  # TODO(stage 4): Sync.SyncPath(path)


class ClouddriveInfoProvider(GObject.GObject, Nautilus.InfoProvider):
    """Per-file sync-status emblems."""

    def update_file_info(self, file):
        # TODO(stage 4): query Sync.StatusForPath(path) and call
        #   file.add_emblem("emblem-synchronizing" | "emblem-default" | ...).
        return Nautilus.OperationResult.COMPLETE
