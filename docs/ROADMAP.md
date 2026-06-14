<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Fiber Elements
-->

# Roadmap

Staged plan. Each stage is independently useful and testable on Fedora 44.

## Stage 0 — Scaffold ✅ (this commit)
- Project layout, licensing, docs, Flatpak manifest.
- Runnable Adwaita shell + module registry + module stubs.
- Nautilus extension stub.

## Stage 1 — Shell + module engine
- `Adw.NavigationSplitView` shell with a real sidebar bound to the account
  registry.
- `Adw.PreferencesWindow` "Modules" page listing toggleable modules.
- Solidify the `ServiceModule` / capability interfaces.

## Stage 2 — Auth core
- MSAL (Graph) device-code + PKCE flow; Google OAuth2.
- Token caches persisted via libsecret / Secret Service portal.
- Entra app registration (public client, native redirect URI) documented in
  [AUTH.md](AUTH.md); Google Cloud OAuth client.

## Stage 3 — OneDrive module v1 (selective sync)
- Wrap `abraunegg/onedrive`: generate config profiles, run `--monitor`, parse
  status, expose selective sync of chosen SharePoint/Teams libraries (one client
  instance per library).
- "Copy share link" via `onedrive --create-share-link`.
- Host user systemd unit management.

## Stage 4 — Nautilus integration
- `nautilus-python` (API 4.0) `MenuProvider` + `InfoProvider`: sidebar entry,
  sync-status emblems, "Sync this folder / Free up space / Copy share link".
- Extension talks to the app's D-Bus status service.

## Stage 5 — OneDrive module v2 (files on-demand)
- Add `onedriver` (FUSE on-demand) and/or `rclone mount` as selectable per-drive
  "sync modes".

## Stage 6 — Mail + Calendar
- `MailProvider` / `CalendarProvider` against **Microsoft Graph** first
  (messages, threads, events, free/busy via `getSchedule`, contacts), then the
  **Gmail API**.
- Optional `eds_reader` to surface existing GNOME accounts.

## Stage 7 — Packaging & polish
- Flatpak on Flathub; Background/autostart portal for the sync service.
- Adaptive UI pass, translations, metainfo screenshots & release notes.

## Known hard limits (set expectations)
- No CFAPI-grade placeholders / kernel overlay icons / seamless dehydration on
  Linux.
- `abraunegg` supports **one SharePoint library per client instance**.
- Some EWS capabilities have no Graph equivalent (public-folder CRUD, certain
  recurring-event delta semantics; tasks live in the To Do API).
