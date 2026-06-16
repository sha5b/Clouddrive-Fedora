# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Pin the GI namespace versions before any cloudy widget import.

Some modules (e.g. ``widgets/source_nav``) do a bare ``from gi.repository import
Gtk`` and rely on the app having required the version first. Test modules import
this one *before* importing those, so discovery order can't break them.

``AVAILABLE`` is False when the Gtk/Adw typelibs aren't installed — e.g. inside a
minimal RPM build chroot during ``%check``. gi-dependent test modules skip
themselves in that case instead of erroring out (the pure-logic tests still run).
No widgets are instantiated here, so no display/``init`` is needed.
"""

import gi

try:
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk  # noqa: F401

    AVAILABLE = True
except (ValueError, ImportError):
    AVAILABLE = False
