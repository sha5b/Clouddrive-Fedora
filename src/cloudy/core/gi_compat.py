# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Version-tolerant GObject-Introspection imports.

Optional integrations (WebKit, Evolution Data Server, the desktop portal) live
in namespaces whose **minor** version varies across GNOME runtimes. Requesting a
single hard-coded version breaks on a newer/older runtime, so we try a list of
candidate versions and let the caller degrade gracefully when none is present.

This is deliberately *not* used for the core ``Gtk`` (4.0) / ``Adw`` (1)
namespaces: those are major API contracts and must stay pinned — silently
accepting GTK 5 / Adwaita 2 would load an incompatible ABI.
"""

from __future__ import annotations

from typing import Iterable

import gi


def require(namespace: str, candidates: Iterable[str]) -> str | None:
    """Require the first available version of ``namespace`` from ``candidates``.

    Returns the version that was selected (or already loaded), or ``None`` if
    none are available — callers should treat ``None`` as "feature unavailable"
    and fall back, never crash.
    """
    for version in candidates:
        try:
            gi.require_version(namespace, version)
            return version
        except ValueError:
            # Either this version isn't installed, or the namespace is already
            # loaded with a different version — try the next candidate.
            continue
    return None
