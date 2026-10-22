# UniMod v0.55 Test 9 — No-archive Nexus discovery fallback

## Added
- Read-only Graveyard Keeper and Graveyard Keeper 2 BepInEx search hints when original Nexus ZIP/.meta files are missing.
- Bounded local manifest (`manifest.json` / `thunderstore.toml`) hints and readable DLL-name fallback; no DLL execution or claim of verified source identity.
- New **Source Matching → Search without Nexus ZIP…** GUI showing local search terms, current game scope, reason/status and one-click official Nexus catalogue search.
- Reject symlinked/out-of-scope DLLs, invalid manifest paths, changed DLL hashes, duplicate entries and mismatched games before searching.
- Re-check installed DLL fingerprint when assigning a result opened through this fallback. All provider results require manual verification and explicit confirmation.
- Fixed README current version display; official AppImage GitHub Actions workflow now targets Test 9 and runs Test 9 GUI smoke.

## Retained
- Exact local Nexus ZIP/.meta evidence from Test 8 is still the stronger separate pathway.
- Nexus downloading/login remains approval-gated. Catalogue lookup is read-only.
- Minecraft Modrinth, Prism/MultiMC, CurseForge read-only catalogue and all pre-existing features retained.

## Validation
- 487 automated Python tests (includes 14 new no-archive fallback tests).
- Virtual-display smoke tested local no-archive GUI, selection guards, provider handoff and no-file-modification behavior.
- Live Nexus API calls and user-installed mod configurations have not been validated.
