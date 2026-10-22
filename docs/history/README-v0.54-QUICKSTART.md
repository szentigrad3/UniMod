# UniMod v0.54 — Minecraft/Modrinth reviewed installation

1. Launch UniMod, open **Discover**, select **Modrinth**, and browse the project's release files. Filter by the Minecraft version and installed loader whenever possible.
2. Select a `.jar` and choose **Download selected to inbox**. UniMod verifies provider hashes and records exact project/version/loader information. Downloading does not modify the game.
3. Open **Provider Inbox**, select the downloaded Modrinth JAR, and choose **Install Modrinth JAR to Prism profile…**.
4. When one Prism/MultiMC instance is found in the standard locations, UniMod selects it automatically. If several (or none) are found, choose the intended instance folder containing `mmc-pack.json`.
5. Review the instance path, Minecraft version, loader, dependency status and file before approval. Close the Minecraft instance first.
6. On success the JAR is copied into the instance's `mods` folder. Managed updates back up the previous version under `~/.config/unimod/recovery/minecraft/`. The download remains in your inbox.

## Limitations

- Only verified `.jar` downloads from Modrinth, for Prism Launcher/MultiMC instances using Fabric, Quilt, Forge or NeoForge. `.mrpack` files, resource packs, shaders, vanilla profiles and unsupported launchers remain download-only.
- Required dependencies must have been installed by UniMod into **that same instance** so their exact Modrinth IDs and file hashes can be verified. UniMod will block a missing or manually installed-but-unidentified dependency. Install dependencies individually first; automatic resolution is not available yet.
- Compatibility is checked against publisher-provided Modrinth version/loader declarations, not independently proven by running Minecraft. Review mod trust, version conflicts and release notes.
- Source provenance is staged for inspection, not assumed from a filename. No authentication secrets are persisted in Modrinth receipts.
- Nexus official OAuth client configuration still awaits Nexus Mods support and public approval. The preexisting Nexus flows remain gated.
