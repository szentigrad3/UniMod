# UniMod v0.47 — Nexus download provenance

- Write token-free, restricted-permissions source receipts after successful reviewed Nexus ZIP downloads.
- Identify matching downloaded ZIPs by SHA-256, even when renamed; preserve UID-to-Nexus source mapping if the ZIP moves or is deleted.
- Integrate receipts into the existing Find mod sources bulk-review workflow, including multi-component modpacks.
- Detect and flag conflicting provenance instead of silently replacing existing Nexus IDs.
- Bound and validate receipt storage; reject symlinks, corrupt receipt databases and oversized files.
- No changes to normal mod installs, update authentication, Nexus SSO approval requirements or review/rollback protections.
- Add offline tests for renamed ZIPs, altered contents, deleted archives, multi-part packages, wrong IDs, conflicts and privacy.
