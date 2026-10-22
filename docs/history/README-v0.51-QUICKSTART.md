# UniMod 0.51 — Linux quick start

1. Make the supplied AppImage executable (`chmod +x UniMod-0.51-Provider-Files-x86_64.AppImage`) and launch it.
2. Open **Discover**, select GitHub or Modrinth, enter a search query, then **Search catalogue**.
3. Select a result and click **Browse release files…**. For Modrinth, optionally filter by Minecraft version and loader (e.g. `1.21.1`, `fabric`).
4. Select a release asset. Check its compatibility, loader and dependency metadata, then click **Download selected to inbox**. Confirm the review prompt.
5. UniMod downloads one selected archive into your configured Downloads folder, validates the archive/size and available provider checksum, and leaves game folders untouched. Installation is **not** automatic.
6. For supported SMAPI/BepInEx ZIPs, use the existing Update Inbox to review identity, version, dependencies, and backups before separately installing. A Minecraft JAR is **not** automatically a compatible SMAPI/BepInEx mod.
7. Nexus authentication for public distribution remains gated until Nexus issues its approved app slug and requirements. `--nexus-readiness` describes pending items.

Privacy: Provider search results are not written into permanent source assignments. No user tokens/API keys are bundled in the AppImage.
