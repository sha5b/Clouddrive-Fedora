<!--
SPDX-License-Identifier: GPL-3.0-or-later
SPDX-FileCopyrightText: 2026 Fiber Elements
-->

# Authentication

All Microsoft 365 / OneDrive / Exchange access goes through **Microsoft Graph**
with **OAuth2**. Google access uses **Google OAuth2** + the Gmail/Calendar APIs.
Tokens are stored via **libsecret**, never in plaintext.

## Microsoft Graph (Entra ID app registration)

1. In the Microsoft Entra admin center, **register an application**.
2. Add a **"Mobile and desktop applications"** platform with redirect URI
   `https://login.microsoftonline.com/common/oauth2/nativeclient` (and/or a
   loopback `http://localhost`). This is a **public client** — no client secret.
3. Enable **"Allow public client flows"**.
4. Delegated scopes (request the subset each module needs):
   - Files: `Files.ReadWrite.All`, `Sites.ReadWrite.All`
   - Mail/Calendar/Contacts: `Mail.ReadWrite`, `Calendars.ReadWrite`,
     `Contacts.ReadWrite`
   - Always: `User.Read`, `offline_access`, `openid`, `profile`

### Auth flow

Use **MSAL for Python** (`msal`):

- **Device code flow** (`initiate_device_flow` / `acquire_token_by_device_flow`)
  — simplest, headless-friendly UX; good default for a desktop app.
- **Authorization code + PKCE** via a loopback redirect — smoother in-app UX.

Persist an MSAL `SerializableTokenCache` into libsecret; refresh silently with
`acquire_token_silent`. Always request `offline_access` for long-lived refresh
tokens.

### Business / tenant caveats

- `*.All` and `Sites.ReadWrite.All` scopes frequently require **tenant admin
  consent**. Treat "an admin must approve this app" as a first-class onboarding
  state.
- Some tenants are "unmanaged" and block third-party apps (`AADSTS65005`) until
  an admin claims the domain.
- **AIP-protected files** report mismatched size/hash via Graph and may fail
  integrity checks — handle in status/error UI.

## Google (Gmail + Calendar)

1. Create a **Google Cloud project** and an **OAuth client** (Desktop app type).
2. Enable the Gmail API and Google Calendar API.
3. Scopes: `gmail.modify` (or finer), `calendar`, plus `openid email profile`.
4. Use the loopback/installed-app OAuth flow; store the refresh token in
   libsecret.

## Why not EWS / Evolution-EWS?

Exchange Web Services soft-blocks for non-Microsoft apps on **2026-10-01** and is
**fully retired 2027-04-01** ("no exceptions and no re-enablement"). Basic Auth
was retired in 2022 and `ApplicationImpersonation` deprecated Feb 2025. Anything
built on EWS has a hard expiry, so Clouddrive targets **Graph** for Exchange.

## Secret storage

`core/secrets.py` wraps libsecret's simple API. Inside the Flatpak sandbox this
transparently uses the **Secret Service portal** with a per-app local keyring —
no broad `--talk-name=org.freedesktop.secrets` hole required.
