# UniMod v0.36 — Nexus registration candidate

- Added official application registration dossier, demo plan and user privacy note.
- Added SSO protocol 2 client (`nexus_integration.py`) gated on Nexus-issued application slug; browser approval and session-only credentials.
- Added explicit Nexus file list, download-to-inbox action and official NXM link parsing for browser-authorized free-account workflows.
- Added strict Nexus URL and game/file-ID checks, HTTPS CDN allowlist, guarded redirects, file size limits, no-overwrite temp-file download handling and mock tests.
- Retained local existing-mod discovery, profiles, source reconciliation, backups and existing update UI.
- No public app approval or real account download verification yet. No embedded API keys.
