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
- Verify pattern used throughout: `python3 -m py_compile`, targeted unit checks
  with mocked API payloads, `meson test` (4 validation tests), and a timed
  launch (`timeout --signal=TERM 4 ./_install/bin/cloudy`, exit 124 = ran OK).

## Credentials (already set up locally; repo is public-safe)
- **Microsoft**: multi-tenant Entra client ID `dcd8ee18-6e62-4c5a-b01f-86f9556f8fed`
  (public client — not a secret). **Google**: Desktop OAuth client.
- Real values live **outside git** in `.env` (repo root, gitignored) and/or
  `~/.config/cloudy/secrets.env`, loaded into `CLOUDY_*` env on startup by
  `core/credentials.py`. The committed repo contains **zero** real IDs/secrets
  (verified). `.env.example` is the template. See `docs/SECRETS.md`.
- Env vars: `CLOUDY_MS_CLIENT_ID`, `CLOUDY_GOOGLE_CLIENT_ID`,
  `CLOUDY_GOOGLE_CLIENT_SECRET` (also GSettings keys; env wins).
- ⚠️ The Google client secret was pasted in chat during setup — **rotate it**
  in Google Cloud Console before any public release.

## How it works (key decisions)
- **Auth**: system browser + loopback. Microsoft = MSAL (`core/auth/msal_graph.py`);
  Google = hand-rolled loopback+PKCE on urllib (`core/auth/google_oauth.py`).
  Tokens in **libsecret** (`core/secrets.py`). Sign-in requests all scopes up
  front (Files+Teams+Mail+Calendar) so one consent covers everything.
- **Files = rclone mounts** (`modules/microsoft365/mounts.py`): rclone does its
  **own** browser auth (built-in app id → no registration), reused per account.
  `authorize(backend)` + `create_remote(remote, backend, opts)` (onedrive +
  drive). Mount → FUSE network drive + a GTK sidebar bookmark → appears in
  Nautilus. **It's a live network drive (two-way), not a synced copy.** Mount
  location + `--vfs-cache-mode` come from Settings.
- **Enumeration** (`modules/microsoft365/graph.py`): `/me/drives`,
  `/me/joinedTeams` → each team's `/groups/{id}/drive` (mounted at team level).
  Google `My Drive` is a synthetic entry mounted via rclone "drive".
- **Mail/Calendar**: `GraphClient` / `GoogleClient` normalized to the same dict
  shapes; provider-agnostic views via `widgets/clients.build_account_client`.
- **Caching**: `core/cache.py` MemoryCache on `app.cache` (stale-while-
  revalidate, 90s TTL) for mail/calendar; Refresh button invalidates per account.
- **Nautilus**: app exports a D-Bus status service (`core/dbus_service.py`);
  host extension `nautilus-extension/cloudy_nautilus.py` draws emblems + menu
  (install via `make install-nautilus`).
- **UI shell** (`window.py`): sidebar (Overview + accounts) → per-account
  `ViewSwitcher` over Files/Mail/Calendar; account ⋮ menu = Sign Out / Remove;
  header Refresh. Modules: `microsoft365` (provider=microsoft),
  `gmail` (provider=google); discovered by `core/plugin_engine.py`.

## Gotchas / conventions (don't relearn the hard way)
- **Pango markup**: Adw row/title/StatusPage text is parsed as markup — a literal
  `&` or `<` breaks it (rendered blank, e.g. `60_R&D`). Always wrap dynamic text
  with `widgets/format.esc()`. Mail list uses plain `Gtk.Label` (immune).
- **Graph URLs**: encode query values with spaces (e.g. `$orderby=... desc`) or
  urllib aborts ("URL can't contain control characters").
- **GSettings**: `Gio.Settings.new()` *aborts the process* if the schema isn't
  installed — look it up via `SettingsSchemaSource` first (see `mounts._setting`).
- **New scopes need re-consent**: existing signed-in accounts must use ⋮ →
  "Sign Out / Re-sign In" to pick up newly-added scopes (e.g. Teams).
- **Google "Testing" publishing status** expires refresh tokens after 7 days and
  caps at 100 testers; publish to production for longer-lived use.
- **meson install doesn't prune**: `make install` removes the installed package
  tree first so renamed/removed modules don't linger as phantom providers.

## Status: done (committed, all builds + 4 meson tests green)
Sign-in (MS + Google, live-verified), Files (OneDrive + all Teams team-level +
Google My Drive), Mount↔Unmount toggle, mail (email-style list, sender names,
read/important/starred, inline reader), calendar (7-day list), Dashboard
(Overview), caching + Refresh, Preferences (mount location / cache mode /
autostart), rclone auto-provision, secrets handling, Nautilus D-Bus + extension.

## Next steps (the backlog)
1. **Mail folders + group/shared mailboxes** — folder switcher
   (Inbox/Sent/Drafts/Archive via `/me/mailFolders`), the M365 **group
   mailboxes** (`/groups/{id}/conversations` — different model than messages),
   and shared mailboxes (`/users/{upn}/messages`). Gmail: label switcher.
2. **Calendar grid** — real month/agenda view (currently a list); event detail;
   maybe write (create/RSVP).
3. **Live transfer status** — mount rclone with `--rc` and poll `core/stats` for
   ↓/↑ activity + speed; feed the D-Bus service so Nautilus shows
   transferring/online; per-file hydration badges from the VFS cache.
4. **Polish** — share links ("Copy share link" via Graph/`onedrive --create-share-link`);
   full-sync mode option (offline copies, distinct from streaming); message
   compose/reply; Flatpak Background portal for real autostart in the sandbox;
   Google Drive **shared drives** (needs Drive scope, re-consent).

## Layout
`src/cloudy/{main,application,window,preferences,account_dialog}.py`,
`core/` (interfaces, plugin_engine, account_registry, secrets, cache,
credentials, provisioner, dbus_service, auth/), `modules/microsoft365/`
(graph, files, mounts, abraunegg), `modules/gmail/` (google_client),
`widgets/` (files/mail/calendar/dashboard/message views, clients, graph_helper,
format). Data in `data/` (gschema, desktop, metainfo, blueprints, icons),
Flatpak manifest `com.fiberelements.Cloudy.yml`.
