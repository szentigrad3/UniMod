# UniMod v0.55 Test 4 — Nexus Mods catalogue for Graveyard Keeper

- Graveyard Keeper and Graveyard Keeper 2 now default source-candidate discovery to the official Nexus Mods catalogue for their own game domains (`graveyardkeeper` / `graveyardkeeper2`), not GitHub-only.
- Uses the documented public GraphQL V2 `mods` query for read-only, game-scoped metadata. No Nexus OAuth, personal API key or file downloads are required or enabled by this feature.
- Strictly validates candidate Nexus mod IDs, source hostname, game domain and explicit manual approval before associating a page with an installed BepInEx DLL. Name searches are NOT binary verification.
- GitHub, Thunderstore, Modrinth, CurseForge and mod.io remain available. The earlier game-specific SMAPI routing fix is preserved.
- Missing/denied Nexus metadata returns an explanation; installed files are never touched. Manual URLs remain a fallback.
- Nexus client registration / OAuth file downloads remain gated pending official approval.
- GraphQL requests and responses are fixture-tested only; public API live connectivity was unavailable in the build environment.
