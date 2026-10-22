# UniMod — Nexus Mods registration dossier (v0.37 development build)

**Registration status:** The maintainer reports sending the Nexus support application. Awaiting Nexus review. No application slug or public approval has been issued yet.

## Application details
- **Application name:** UniMod
- **Version:** 0.37.0 (experimental Linux testing build)
- **Developer/contact:** Application maintainer; reply address to be supplied by sender of registration email.
- **Platforms:** Linux x86_64 (initially CachyOS/Arch; other Linux distributions may be supported later)
- **License:** MIT for UniMod's original application source; bundled third-party runtime dependencies retain their own licenses.
- **Description:** UniMod is a Linux mod manager that discovers existing mods across Steam, Heroic and Lutris games; identifies installed Stardew Valley SMAPI and BepInEx mods, checks updates via official API IDs, and manages reviewed downloads and backups. It supports Nexus Mods and Thunderstore as separate integrations.
- **Provided logo:** `unimod-nexus-logo-512.png` (512px, visible on dark backgrounds; scaled from existing project logo)

## Official Nexus requirements
Per https://help.nexusmods.com/article/114-api-acceptable-use-policy, contact **support@nexusmods.com** with a working API test build, then provide app name, description and logo and incorporate any requested changes. Nexus issues an approved application slug for SSO. Do not publish a personal API key or imply approval before Nexus confirms it.

## Authentication and key lifecycle
- **Testing**: user enters *their own personal API key* in a masked field. This is for private development tests only.
- **Public use after registration**: `UNIMOD_NEXUS_APP_SLUG` is populated with the slug *issued by Nexus*. The `Connect Nexus account` button uses `wss://sso.nexusmods.com`, SSO protocol 2, opens the official site in the system browser and receives a per-user key.
- API keys are held in **process memory only** and cleared on app exit or by the Clear Key button.
- No app secrets or user keys are hardcoded, written to config, logged or sent to a UniMod server.
- Users can revoke authorization from their Nexus Mods account's API Access page.
- Supported v1 API calls send `Application-Name: UniMod`, `Application-Version: 0.37.0`, and `apikey` over HTTPS.

## Requested download workflows
1. Authenticated user selects the *exact Nexus mod* identified from a recognised ID or confirmed source URL.
2. File listing uses the official `GET /v1/games/{game}/mods/{mod_id}/files.json` endpoint. The user selects one exact file rather than letting UniMod pick arbitrary/latest files.
3. For accounts authorised to obtain direct links (e.g. Premium where supported), UniMod asks the v1 `download_link.json` endpoint. It only follows approved HTTPS CDN URLs and writes to the user's Downloads inbox without altering game files.
4. Free-account downloads follow the official browser flow, including site-created `nxm://` links carrying short-lived tokens. A user can paste an NXM link into UniMod; it will not bypass the Nexus site or account restrictions. The game and mod IDs must match.
5. Installation is a separate user-confirmed action with existing backups/rollback safeguards; downloading does **not** auto-install.
6. Files with mod-manager downloads disabled or accounts without required permissions are not downloaded directly.

## Network endpoints
- `https://api.nexusmods.com/v1/` (API requests)
- `wss://sso.nexusmods.com` (SSO *only after registered slug*)
- `https://www.nexusmods.com/sso?...` (browser approval)
- `https://www.nexusmods.com/{game}/mods/{id}` (official mod pages, user opened)
- HTTPS download mirrors only under `*.nexusmods.com` / `*.nexus-cdn.com` (no HTTP and no bypass)

## Requested clarification from Nexus
- Confirm whether the v1 read/download endpoints are still preferred for newly registered standalone managers or whether Nexus wants a supported v3/v2 route.
- Confirm the assigned SSO application slug, any required extra headers, allowed scopes and standard NXM handler registration guidance.
- Confirm CDN allowlist expectations and free/Premium rules for file downloads.
- Confirm whether Nexus wants a separate application registration per public build or one registration for UniMod as a product.

## Test procedure supplied to Nexus
See `NEXUS-TEST-PLAN.md`. Please *do not* send a personal API key with the email, screenshots or source bundle.

## Security boundaries
SSO is not activated without a registered slug, and it has not yet been tested live. Local tests use injected protocol/HTTP fixtures. No mass scraping, no user-key server-side storage, no affiliate bypass, no automatic bulk download. Rate-limit HTTP 429 errors are surfaced to the user. UniMod's existing update checks are user-initiated and capped at 25 unique Nexus IDs per batch.

## UniMod 0.37: browser integration and reviewed queue
UniMod adds an **opt-in** Linux handler for `nxm://` links. A browser click passes a short-lived token to a new UniMod process; the token is kept in memory and is **never copied into queue exports, logs or installation receipts**. The user must select and approve the queued download. No automatic installation occurs.

`--register-nxm` installs a per-user desktop MIME handler. A handler registration must be repeated if the AppImage is moved. Public releases must still be approved by Nexus; this feature alone does not grant API/download privileges.
