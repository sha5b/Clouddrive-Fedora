<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Fiber Elements
-->

# Cloudy — Handoff / Continue Here

Pick-up doc for a fresh session. Cloudy is a **GTK4 / Libadwaita (Python /
PyGObject)** super-app for **Microsoft 365 (OneDrive + Teams/SharePoint, Mail,
Calendar)** and **Google (Gmail, Calendar, Drive)** on Fedora 44 (GNOME 50). It
*orchestrates* proven backends (rclone for mounts; Microsoft Graph / Google REST
for mail/calendar) rather than reimplementing them. Read `docs/ARCHITECTURE.md`,
`docs/AUTH.md`, `docs/SECRETS.md`, `docs/ROADMAP.md` for depth.

## Build / run / test
```bash
cd <repo>
make run            # meson build+install into _install, then launch ./_install/bin/cloudy
make build|test|lint|clean
make flatpak flatpak-run   # sandboxed (org.gnome.Platform 50)
```
- Dev toolchain here is **user-space**: `meson`/`ninja` via `pip --user`
  (`export PATH="$HOME/.local/bin:$PATH"`); `blueprint-compiler` auto-fetched via
  the wrap; `msal` via `pip --user`. `rclone` is **auto-provisioned** (rootless)
  into `~/.local/share/cloudy/bin/rclone` on first run; also bundled in the Flatpak.
- The app is **single-instance** (GApplication) — quit the running one before
  relaunching, or a new launch just hands off and exits 0.
- `make lint` is just `py_compile` (no pyflakes/ruff installed here). Useful extra
  checks: `python3 -m py_compile <files>`; a **headless import smoke test**
  (`gi.require_version` then `importlib.import_module` each widget module —
  catches missing imports/NameErrors without a display). NOTE: `window.py` can't
  be imported standalone (its `Gtk.Template` needs the compiled gresource); skip
  it in smoke tests. `meson test` runs 4 validation tests (desktop/schema/
  metainfo/blueprint).
- **Driving the GUI from a headless/agent shell fails** (the Wayland app handoff
  signals and kills the wrapper shell, exit 144) — verify via build + tests +
  import/logic smoke, then ask the user to `make run` to eyeball.

## Credentials (already set up locally; repo is public-safe)
- **Microsoft**: multi-tenant Entra client ID `dcd8ee18-6e62-4c5a-b01f-86f9556f8fed`
  (public client — not a secret). **Google**: Desktop OAuth client.
- Real values live **outside git** in `.env` (repo root, gitignored) and/or
  `~/.config/cloudy/secrets.env`, loaded into `CLOUDY_*` env on startup by
  `core/credentials.py`. The committed repo contains **zero** real IDs/secrets.
  `.env.example` is the template. See `docs/SECRETS.md`.
- Env vars: `CLOUDY_MS_CLIENT_ID`, `CLOUDY_GOOGLE_CLIENT_ID`,
  `CLOUDY_GOOGLE_CLIENT_SECRET` (also GSettings keys; env wins).
- ⚠️ The Google client secret was pasted in chat during setup — **rotate it**
  in Google Cloud Console before any public release.

## How it works (key decisions)
- **Auth**: system browser + loopback. Microsoft = MSAL (`core/auth/msal_graph.py`);
  Google = hand-rolled loopback+PKCE on urllib (`core/auth/google_oauth.py`).
  Tokens in **libsecret** (`core/secrets.py`). Sign-in requests **all** scopes up
  front (Files+Teams+Groups+Mail+Calendar+**Mail.ReadWrite.Shared**) so one
  consent covers everything, **including shared mailboxes/calendars**.
- **Shared/group sources**: Graph `list_shared_folders` / `list_shared_events`
  use `/users/{address}` + `Mail.ReadWrite.Shared`; group mail/calendars use
  `/groups/{id}` + `Group.Read.All`. IDs are prefixed `shared:<addr>:` /
  `group:<id>:` so `get_message`/`get_event` route back correctly. Accessing your
  **own** address as a "shared" source returns Graph 403 ErrorAccessDenied —
  that's expected (use the **Me** source for your own mailbox).
- **Mail & Calendar share one source model** (Microsoft only): **Me / Teams /
  Shared** tabs. The common scaffolding lives in **`widgets/source_nav.py`**:
  `SourceTabs`, `run_async(work, on_done)` (the off-thread→idle_add helper used by
  every view), `clear_listbox`, `message_row`/`action_row` placeholders,
  `is_scope_error`, `present_add_shared_dialog`, and the **pin** helpers
  (`toggle_pin`/`is_pinned`/`find_pin`). When a shared/group call fails for lack
  of scope, the view shows a **Re-sign in** action row (re-consent grants the new
  scope; everyday mail keeps working).
- **Files = rclone mounts** (`modules/microsoft365/mounts.py`): rclone does its
  **own** browser auth (built-in app id → no registration), reused per account.
  Mount → FUSE network drive + a GTK sidebar bookmark → appears in Nautilus.
  **It's a live network drive (two-way), not a synced copy.** Cache mode + mount
  location come from Settings. **Mount layout** (`mount-layout` setting): either
  `one-folder` (everything under the global mount location) or `individual` (each
  account picks its own folder via `Account.mount_location`). `mountpoint_for`/
  `mount` take an optional `base` override; `account_mount_base(loc)` resolves it.
- **In-app file browser** (`widgets/file_browser.py`): the Files tab is an
  `Adw.NavigationView` — **Libraries** (mount toggles) at the root; a *mounted*
  library row is clickable → pushes a `FileBrowserPage` that lists the mountpoint
  (folders first, drill in, click a file → opens in the default app). Listing
  runs off-thread; `recent_changes(roots)` (bounded scan) powers the Dashboard.
- **Offline sync** (`core/sync.py`): when `default-sync-type` = `full` and an
  account's per-account toggle is on, `SyncManager` runs `rclone bisync` into
  `…/cloudy/synced` on a timer. When type = `stream`, the per-account toggle is
  disabled (mounting stays manual). Streaming auto-mount-on-login is **not** built.
- **Caching**: `core/cache.py` MemoryCache on `app.cache` (stale-while-
  revalidate, 90s TTL) for mail/calendar; per-source cache keys; Refresh
  invalidates per account.
- **Nautilus**: app exports a D-Bus status service (`core/dbus_service.py`); host
  extension draws emblems + menu (`make install-nautilus`).
- **UI shell** (`window.py`): sidebar (Overview + accounts) → per-account
  `ViewSwitcher` over Files/Mail/Calendar; header Refresh.
  `open_mail(account, mid)` and `open_account_tab(account, tab)` are deep-link
  entry points used by the Dashboard. A **turned-off** account (its module
  disabled) shows "Turned off" in the sidebar and a disabled status page.
- **Dashboard** (`widgets/dashboard_view.py`): **Pinned** (starred shared/group
  sources with live counts, click to jump) → **Upcoming** (your calendars) →
  **Recent mail** → **Recent file changes** (newest edits in mounted/synced dirs).
- **Preferences** (`preferences.py`), two pages only:
  - **General** — Mount location · Mount layout · File caching · Sync type
    (stream/full) · Start at login.
  - **Accounts** — each account is an `ExpanderRow`: an **on/off switch** for its
    services (replaces the old Modules tab → `enabled-modules` setting), Sign
    In/Out, Remove; expands to **Sync files offline** + **Mount location** (both
    shown but greyed until their General prerequisite is set).
- **Pinning ("star")**: the ★ button in Mail/Calendar (Teams/Shared sources)
  toggles `Account.pinned_sources` entries
  `{kind: mail|calendar, source: shared|teams, id, name}`; the Dashboard renders
  them.

## Gotchas / conventions (don't relearn the hard way)
- **Use `source_nav.run_async`** for off-thread work, not raw
  `threading.Thread`+`GLib.idle_add` — callback signature is `(result, error)`;
  capture extra ids via a lambda (`lambda res, err: self._on_x(id, res, err)`).
- **Pango markup**: Adw row/title/StatusPage text is parsed as markup — wrap
  dynamic text with `widgets/format.esc()`. Mail/agenda lists use plain
  `Gtk.Label` (immune).
- **Graph URLs**: encode query values with spaces (e.g. `$orderby=... desc`) or
  urllib aborts ("URL can't contain control characters").
- **GSettings**: `Gio.Settings.new()` *aborts the process* if the schema isn't
  installed — look it up via `SettingsSchemaSource` first (see `mounts._setting`).
  New schema keys need `make build` (recompiles + reinstalls the schema).
- **New scopes need re-consent**: existing accounts must re-sign-in (Preferences →
  Accounts → Sign Out, then Sign In) to pick up newly-added scopes. The Mail/
  Calendar views surface this with an inline **Re-sign in** button on scope errors.
- **`Account` model** (`core/account_registry.py`): `from_dict` tolerates missing
  keys, so adding fields is safe; removing a field just drops it on next save
  (this is how `group_calendars` was retired). Current extra fields:
  `full_sync`, `mount_location`, `shared_mailboxes`, `pinned_sources`.
- **Network-mount scans are dangerous**: `os.walk` over a FUSE mount can stall /
  trigger downloads. `recent_changes` is bounded by `max_scan`; keep any new
  scanning bounded too.
- **Module on/off is per-provider**: the Accounts on/off switch toggles the whole
  `module_id` (`enabled-modules`), so all accounts of a provider share it.
- **Google "Testing" publishing status** expires refresh tokens after 7 days;
  publish to production for longer-lived use.
- **meson install doesn't prune**: `make install` removes the installed package
  tree first so renamed/removed modules don't linger.

## Status: done (working, all builds + 4 meson tests green)
Sign-in (MS + Google), Files (OneDrive + Teams + Google My Drive) with
Mount↔Unmount **and an in-app file browser**, Mail and Calendar both with
**Me/Teams/Shared** sources + shared-mailbox add + **★ pin to Dashboard** + inline
re-sign-in on scope errors, message reader, event detail + RSVP, **reworked
Dashboard** (pinned/upcoming/mail/file-changes), **reorganized Preferences**
(General vs Accounts; per-account services on/off, offline-sync toggle, mount
location; **Modules tab removed**), mount layout (one-folder/individual) +
per-account mount location, caching + Refresh, rclone auto-provision, secrets,
Nautilus D-Bus + extension. Shared view code deduped into `widgets/source_nav.py`.

## Next steps (the backlog)
1. **Verify shared/group sources end-to-end** against a *real* shared mailbox /
   group the user has delegated access to (not their own address — that 403s).
2. **Streaming sync activation** — make the per-account toggle, when sync type =
   `stream`, actually auto-mount the account's libraries at startup (today it's
   disabled; only `full` bisync is wired).
3. **Calendar grid** — real month/agenda view (currently a 7-day list).
4. **Live transfer status** — mount rclone with `--rc`, poll `core/stats` for
   ↓/↑ activity; feed the D-Bus service so Nautilus shows transferring/online.
   This is also the better long-term source for the Dashboard "Recent file
   changes" than walking the mount.
5. **Compose/reply** for mail; **file ops** (rename/delete/upload) in the browser.
6. **Multi-account-per-module**: the Accounts on/off switch currently toggles the
   whole module (all accounts of that provider). If multiple same-provider
   accounts become common, add a real per-account `enabled` flag.

## Layout
`src/cloudy/{main,application,window,preferences,account_dialog}.py`,
`core/` (interfaces, plugin_engine, account_registry, secrets, cache,
credentials, provisioner, dbus_service, sync, auth/), `modules/microsoft365/`
(graph, files, mounts, abraunegg), `modules/gmail/` (google_client),
`widgets/` (files/mail/calendar/dashboard/message/event views, **source_nav**,
**file_browser**, clients, graph_helper, format). Data in `data/` (gschema,
desktop, metainfo, blueprints, icons), Flatpak manifest
`com.fiberelements.Cloudy.yml`.
```
widgets/source_nav.py   shared: SourceTabs, run_async, listbox/placeholder
                        helpers, is_scope_error, add-shared dialog, pin helpers
widgets/file_browser.py in-app browser (FileBrowserPage) + recent_changes()
```
