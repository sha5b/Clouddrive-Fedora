# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Shahab Nedaei
"""A tiny in-memory cache for API results (stale-while-revalidate).

Lives on the Application so it survives view rebuilds: switching accounts or
tabs redisplays instantly from cache, then refreshes in the background. Keyed by
strings like "<account_id>:messages:inbox".
"""

from __future__ import annotations

import threading
import time


class MemoryCache:
    def __init__(self, ttl: float = 90.0):
        self._ttl = ttl
        self._store: dict[str, tuple[float, object]] = {}
        # Reads/writes come from both the GTK main loop and the off-thread
        # workers (run_async); a lock keeps the dict from being mutated mid-
        # iteration ("dictionary changed size during iteration").
        self._lock = threading.Lock()

    def get(self, key: str):
        """Return (value, is_fresh) if cached, else None."""
        with self._lock:
            entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        return value, (time.monotonic() - ts) < self._ttl

    def set(self, key: str, value) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def invalidate(self, prefix: str | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._store.clear()
            else:
                self._store = {k: v for k, v in self._store.items()
                               if not k.startswith(prefix)}
