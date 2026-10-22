# UniMod 0.37 — Nexus browser link handling

- Added reviewed, session-only Nexus download queue in Downloads.
- Added explicit user opt-in Linux `nxm://` handler integration via `xdg-mime`.
- Accepts `--nxm <url>` from desktop browser launch; rejects expired or invalid links.
- Nexus file choice now queues rather than immediately downloads.
- Token-safe status display and redacted download errors.
- Validates ZIP/7z/RAR file signatures before saving a Nexus queue download; fixes extension for NXM downloads.
- Added 11 new queue, security and desktop handler tests; existing functionality preserved.

**Limitations:** A browser click opens a new UniMod process. API file access remains subject to Nexus authorization; public SSO unavailable until Nexus issues a registered app slug. No automated installation.
