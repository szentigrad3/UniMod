# UniMod v0.55 Test 7 — reviewed CurseForge metadata

- **CurseForge game verification:** query the official `/v1/games/{gameId}` metadata endpoint using an approved, session-only API key; show returned game title and require user confirmation before catalogue searching.
- **Read-only release preview:** list file name, release type, game versions, published date, and size from `/v1/mods/{modId}/files`, limited to the first 50 records. Never expose or use download URLs; no file downloads or installations.
- **Game-ID scoping:** reject mismatched game ID in CurseForge search hits and file listings, and reject a reviewed source assignment if the verified game does not match the installed game.
- **Key-scoped sessions:** changing the CurseForge key or game ID invalidates previous approval for searches and previews. Keys stay in memory and out of mod metadata and result records.
- **Safety:** HTTPS API allowlist, bounded response length, read-only requests, explicit source assignment review and preserved Nexus OAuth registration gate.
- Corrected GUI release labels to v0.55 Test 7; updated CI build artifacts and smoke tests.
- Seven new offline API tests and one GUI smoke test; **453 total Python tests** pass on the release tree. Existing game/source and modpack GUI tests pass.

**Limitations:** A CurseForge API key approved for UniMod use is required. No server credentials were provided in testing, so the real CurseForge API remains untested. Downloads/installs from CurseForge are intentionally disabled. Modrinth .mrpack importing remains experimental. Nexus OAuth/download features still require official provider registration.

**Packaging:** The provided portable executable is a custom self-extracting Linux x86_64 ELF using bundled Python/Tk and system `tar`, not an official AppImageKit image. `build-appimage.sh` and CI remain the supported path to create an official Type 2 AppImage.
