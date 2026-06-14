# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""Load OAuth credentials from dotenv files, never from committed source.

On startup we populate ``CLOUDY_*`` env vars from the first file that defines
them, in priority order (a key already in the environment always wins):

  1. ``$CLOUDY_ENV_FILE`` (explicit override)
  2. ``./.env`` — the project ``.env`` (copied from ``.env.example``; gitignored)
  3. ``$XDG_CONFIG_HOME/cloudy/secrets.env`` — a user-global fallback

The app's getters read CLOUDY_MS_CLIENT_ID / CLOUDY_GOOGLE_CLIENT_ID /
CLOUDY_GOOGLE_CLIENT_SECRET. For shipped builds, a release pipeline injects the
same values from a CI secret store. See docs/SECRETS.md.
"""

from __future__ import annotations

import os

from gi.repository import GLib

_PREFIX = "CLOUDY_"


def _candidate_paths() -> list[str]:
    paths = []
    explicit = os.environ.get("CLOUDY_ENV_FILE")
    if explicit:
        paths.append(explicit)
    paths.append(os.path.join(os.getcwd(), ".env"))
    paths.append(os.path.join(GLib.get_user_config_dir(), "cloudy", "secrets.env"))
    return paths


def _apply(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key.startswith(_PREFIX) and not os.environ.get(key):
            os.environ[key] = value


def load_local_env() -> None:
    """Populate CLOUDY_* env vars from the first dotenv file that defines them."""
    for path in _candidate_paths():
        _apply(path)
