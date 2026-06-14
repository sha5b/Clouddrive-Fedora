# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Fiber Elements
"""Mirror Cloudy events into a local Evolution Data Server (EDS) calendar.

GNOME Shell's top-bar calendar reads from EDS, so to make Cloudy events show
there we keep a dedicated local calendar named "Cloudy" and create/update VEVENT
components in it from the normalized event dicts the views already load.

This is **best-effort and fully guarded**: EDS (libecal/libedataserver via GI)
may be missing or unreachable (e.g. inside a sandbox). Any failure disables the
feature for the session rather than disturbing the app. Honours the
``eds-publish-enabled`` GSetting (off by default).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

_CAL_NAME = "Cloudy"
_PRODID = "-//Fiber Elements//Cloudy//EN"


def _log(msg: str) -> None:
    print(f"[eds] {msg}")


def _parse_utc(value: str) -> datetime | None:
    if not value or "T" not in value:
        return None
    txt = value.strip()
    try:
        dt = datetime.fromisoformat(txt.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromisoformat(txt.split(".", 1)[0])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _esc(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;") \
        .replace(",", "\\,").replace("\n", "\\n")


def _vevent(uid: str, ev: dict) -> str | None:
    """Build a VEVENT block for one normalized event, or None if untimed/bad."""
    summary = ev.get("subject") or "(no title)"
    if ev.get("all_day"):
        start = _parse_utc(ev.get("start", "")) or _date_only(ev.get("start", ""))
        end = _parse_utc(ev.get("end", "")) or _date_only(ev.get("end", ""))
        if start is None:
            return None
        ds = start.strftime("%Y%m%d") if isinstance(start, datetime) else start
        de = (end.strftime("%Y%m%d") if isinstance(end, datetime)
              else end) if end else ds
        dt_lines = f"DTSTART;VALUE=DATE:{ds}\r\nDTEND;VALUE=DATE:{de}"
    else:
        start = _parse_utc(ev.get("start", ""))
        end = _parse_utc(ev.get("end", "")) or (start + timedelta(hours=1) if start else None)
        if start is None or end is None:
            return None
        dt_lines = (f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}\r\n"
                    f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}")
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SUMMARY:{_esc(summary)}",
        dt_lines,
    ]
    if ev.get("location"):
        lines.append(f"LOCATION:{_esc(ev['location'])}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines)


def _date_only(value: str):
    if value and len(value) >= 10:
        return value[:10].replace("-", "")
    return None


def publish_events(app, account, events) -> None:
    """Create/update the given events in the local 'Cloudy' EDS calendar.

    Safe to call from a worker thread (EDS sync calls block). No-ops when the
    setting is off or EDS is unavailable; never raises."""
    try:
        if not app.settings.get_boolean("eds-publish-enabled"):
            return
    except Exception:  # noqa: BLE001
        return
    if getattr(app, "_eds_disabled", False):
        return
    client = _get_client(app)
    if client is None:
        return

    from .gi_compat import require

    if require("ECal", ("2.0", "3.0")) is None or \
            require("ICalGLib", ("3.0", "4.0")) is None:
        return  # EDS not available on this runtime
    from gi.repository import ECal, ICalGLib

    for ev in events or []:
        uid = f"cloudy-{account.id}-{ev.get('id', '')}@cloudy"
        block = _vevent(uid, ev)
        if block is None:
            continue
        try:
            icomp = ICalGLib.Component.new_from_string(block)
            if icomp is None:
                continue
            existing = None
            try:
                existing = client.get_object_sync(uid, None, None)
            except Exception:  # noqa: BLE001 - not present yet
                existing = None
            if existing is not None:
                client.modify_object_sync(
                    icomp, ECal.ObjModType.ALL, ECal.OperationFlags.NONE, None)
            else:
                client.create_object_sync(icomp, ECal.OperationFlags.NONE, None)
        except Exception as exc:  # noqa: BLE001 - one bad event shouldn't abort
            _log(f"skip event: {exc}")


def _get_client(app):
    """Lazily build (and cache) the ECal client for the Cloudy calendar."""
    client = getattr(app, "_eds_client", None)
    if client is not None:
        return client
    try:
        from .gi_compat import require

        if require("EDataServer", ("1.2", "1.3")) is None or \
                require("ECal", ("2.0", "3.0")) is None:
            raise RuntimeError("EDS namespaces unavailable")
        from gi.repository import EDataServer, ECal

        registry = EDataServer.SourceRegistry.new_sync(None)
        source = _find_or_create_source(EDataServer, registry)
        client = ECal.Client.connect_sync(
            source, ECal.ClientSourceType.EVENTS, 30, None)
        app._eds_client = client
        return client
    except Exception as exc:  # noqa: BLE001 - disable for the session
        _log(f"unavailable, disabling: {exc}")
        app._eds_disabled = True
        return None


def _find_or_create_source(EDataServer, registry):
    ext = EDataServer.SOURCE_EXTENSION_CALENDAR
    for source in registry.list_sources(ext):
        if source.get_display_name() == _CAL_NAME:
            return source
    source = EDataServer.Source.new(None, None)
    source.set_parent("local-stub")
    source.set_display_name(_CAL_NAME)
    backend = source.get_extension(ext)
    backend.set_backend_name("local")
    registry.commit_source_sync(source, None)
    return source
