# UniMod 0.50 — Provider catalogues and Nexus approval handoff

## Nexus integration readiness
- Existing private-test API key, registered-app SSO protocol, browser NXM download links, single-instance forwarding, file list and reviewed downloads are preserved.
- Existing user-confirmed installation preflight, backups, receipts and rollback remain unchanged.
- Application HTTP request identification now reports version 0.50.0.
- `python unimod.py --nexus-readiness` reports the local prerequisites and the information needed from Nexus. It **does not** claim Nexus has approved UniMod or that production authentication has been tested.
- The exact Nexus-issued slug is supplied as an environment variable `UNIMOD_NEXUS_APP_SLUG`, never guessed or bundled. Live SSO and authorization tests still require approval. A reviewer can use the private development key feature with their own key.

## Multi-provider online discovery
- Replaced the static Discover page with a searchable, read-only catalogue covering GitHub, Modrinth and Thunderstore.
- Added opt-in, credential-gated read-only searches for CurseForge and mod.io. Keys are held in the application session only. This isn't a public sign-in substitute; provider permission is required.
- Results show the provider, title, author and summary, and open provider-controlled official pages. Search by name is **never** treated as proof of an installed mod's identity.
- Bounded results and network reads, HTTPS-only fixed API hosts, safe link construction and redirects restricted to the same API host.
- No bulk scraping, unattended mass downloads, automatic source assignment or mod installation from search results.

## Unfinished/approval-dependent
- Nexus: approval, issued app slug, provider response on current supported API/download endpoints; then live SSO and free/Premium download tests.
- CurseForge: developer/provider API approval and confirmed permitted usage for a public app.
- mod.io: API key and game-specific permissions, and future approved OAuth/subscription support.
- Steam Workshop: Steam-supported/Workshop-managed workflow per game; no bypass downloading.
- ModDB: browser opening only; no unofficial scraping or fake API integration.
- AppImage: still uses the experimental extract-and-run runtime, not official AppImageKit.
