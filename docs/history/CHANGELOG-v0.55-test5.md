# UniMod v0.55 Test 5 — Reviewed Minecraft Modrinth modpack import

- Adds reviewed installation of staged `.mrpack` archives into **existing** Prism Launcher / MultiMC profiles.
- Requires exact Minecraft version, mod loader **name and version** matching `mmc-pack.json` before changes.
- Restricts modpack output to approved Minecraft content/config folders, blocks path traversal/symlinks/special ZIP entries and refuses unsupported download hosts.
- Downloads required client files only from the Modrinth CDN, verifies exact sizes and both SHA-1 + SHA-512 **before game writes**, and blocks redirected downloads to other hosts.
- Applies regular and client overrides with client precedence. Server-only and optional client downloads are skipped; game saves and launcher metadata cannot be overwritten.
- Shows the number of writes, overwrites, backup size and download size for explicit approval. Backs up files to the UniMod recovery folder and restores modifications if installation fails.
- Preserves all v0.55 Test 4 Graveyard Keeper Nexus catalogue/source-review functionality and Nexus registration gate.
- Fixes a stale Test 1 filename in the AppImage GitHub Actions smoke/upload workflow; adds `.mrpack` GUI regression coverage.

**Limits:** Does not create new Prism/MultiMC instances or install/update loaders; only already-compatible instances. No optional-file picker yet. Packs requiring GitHub/GitLab downloads or unrestricted override paths are deliberately blocked. Test fixtures simulate CDN downloads; actual downloads and target-system behaviour require validation on CachyOS. Keep Minecraft closed while importing.
