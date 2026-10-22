# UniMod v0.55 Test 8 — Graveyard Keeper Nexus archive evidence

## Added
- Read-only, offline local download ZIP scanning for both Graveyard Keeper and Graveyard Keeper 2 BepInEx mods.
- Exact SHA-256 comparison of installed DLLs to DLL members of downloaded ZIP files with MO2 `.meta` sidecars.
- Separate game-domain checks for `graveyardkeeper` and `graveyardkeeper2`.
- Candidate review with archive name, Nexus page, and explicit confirmation before persisting any source assignment.
- Multi-selection saves with game-change, known-source, conflict and file-changed protections.
- Hard limits for archive size, item count, per-file sizes and cumulative data; ZIP path traversal and symlinks cannot become installation paths.

## Not enabled
- No Nexus login, downloads, automatic identity claiming or game-file modification.
- Unknown provenance without metadata stays `Source needed`.

## Validation
- 473 automated unit tests, including 20 new offline archive provenance tests.
- New GUI approval / game-switch test plus existing provider GUI regression checks.
- Live Nexus provider access and actual CachyOS installation remain untested.
