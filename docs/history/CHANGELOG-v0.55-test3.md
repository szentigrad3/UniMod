# UniMod v0.55 Test 3 — Reviewed source discovery for BepInEx games

- **Graveyard Keeper / BepInEx workflow:** On **Source Matching**, select an installed mod and click **Find candidate pages…**. UniMod carries that exact game/mod selection into **Mod Websites** and searches the public GitHub catalogue using the mod display name.
- Candidate results are NOT assumed to identify installed binaries. Open the official page and check the publisher, supported game, mod details and version.
- **Link reviewed page to selected mod…** offers an explicit confirmation; only validated HTTPS links on supported mod-hosting websites are saved to UniMod's source-assignment configuration. It never edits the installed DLL, changes a loader or downloads a mod.
- Blocks stale or game-changed selections, absent/ambiguous installed-mod identities, missing result selections and unsupported link domains.
- Keeps SMAPI automatic source lookup restricted to Stardew Valley. Nexus OAuth remains approval-gated.
- 418 Python unit tests and additional GUI smoke tests passed in a virtual Linux session. Live GitHub catalogue lookup and the user's actual Graveyard Keeper installation have not been tested.
- Bundled Linux executable uses a **custom portable extraction runtime** and is not claimed to be a standard AppImageKit Type 2 image.
