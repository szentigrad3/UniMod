# UniMod 0.50 quick start (CachyOS / Linux)

1. Run `chmod +x UniMod-0.50-x86_64.AppImage` and `./UniMod-0.50-x86_64.AppImage`.
2. UniMod discovers installed game mods. Select **Discover** (magnifying glass rail icon).
3. Choose GitHub or Modrinth, enter a query, then **Search catalogue**. For Thunderstore also enter a community such as `valheim`.
4. Double-click a result to open the official project page. Search results do not install files or change your game.
5. CurseForge and mod.io require a provider-approved API key and numerical game ID. The key field is masked, session-only, and never written to settings. Search failures never display keys.
6. Nexus testing uses **Tools → Sources & updates → Nexus Updates**. Public SSO remains unavailable until Nexus issues UniMod its official application slug. For readiness, run `./UniMod-0.50-x86_64.AppImage --nexus-readiness`.

The existing game-management, safe update installation, source-recognition and backup/restore features remain available. This is a testing build, not a general-public Nexus authorization.
