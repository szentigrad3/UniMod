# UniMod v0.39 — download progress and safe cancellation

- Progress by bytes / percent for active Nexus downloads, using response Content-Length when available.
- Cooperative cancel button cancels current stream and skips remaining jobs, without leaving .part files.
- Retry failed/cancelled requests only when explicitly chosen; expired NXM links need reopening on Nexus.
- Review completed ZIP sends it to existing Update Inbox preflight; install remains separate and requires backup confirmation.
- Completed / cancelled / error statuses are shown individually; no credential, URL token or CDN link is persisted.
- Supported Nexus account permissions are unchanged; application registration and live SSO remain pending.

Progress and cancel are best-effort while a network read is blocked. The download timeout still applies.
