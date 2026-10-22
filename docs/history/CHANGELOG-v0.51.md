# UniMod v0.51 — Reviewed provider release files

- GitHub: browse published release assets from the selected repository. Draft, prerelease, unsafe-link and non-archive assets are excluded. Game compatibility is **not** asserted from generic GitHub metadata.
- Modrinth: browse project versions and file variants; optional exact Minecraft game-version and mod loader filters; show declared dependencies. Download only selected files.
- Both providers: explicit review before download, HTTPS origin/redirect restrictions, bounded sizes, archive format check, verify SHA-1/SHA-256/SHA-512 when provided, exclusive destination creation, and temporary file cleanup on failure.
- Downloads are staged in the configured Downloads folder; they are not installed, deployed, connected to installed mods, or trusted just because a name matches.
- Nexus registration remains pending; no production SSO or free/Premium restrictions were bypassed. CurseForge/mod.io continue to require approved credentials and have catalogue-only support.
- Experimental standalone AppImage build retains the existing extract-and-run runtime.

**Limits:** Modrinth file listing is intended for Minecraft profiles; UniMod does not yet install Minecraft loader dependencies or provision Minecraft profiles. GitHub releases have no standard game-compatibility metadata. 7z/RAR signature checks are not exhaustive, and provider hashes may be missing. Live API/download behavior remains unverified on the user's desktop.
