# UniMod 0.54 — Verified Prism/MultiMC Modrinth JAR deployment

- Added read-only discovery of existing Prism Launcher and MultiMC instances in standard Linux and Flatpak directories. Symlinks are not followed, and the scan is bounded.
- Added Prism instance validation via `mmc-pack.json`: installed Minecraft version and **exactly one** Fabric, Quilt, Forge or NeoForge loader must be identifiable before installation.
- Added **Provider Inbox → Install Modrinth JAR to Prism profile…**. Exact provider file receipts, SHA-256, archive structure, supported game version and loader are checked before the user approves writing to the chosen profile.
- Implemented managed new installs and backup-protected updates in the selected profile's `mods` directory; changed unmanaged files, collisions and ambiguous profile states fail closed. Receipt failures restore the former JAR where possible.
- Required Modrinth dependencies must be verifiably present in that instance through UniMod's own installation receipts; optional dependencies are shown but not downloaded automatically. Recorded dependency project/version IDs are preserved when staging files.
- Modrinth downloads are unbound to unrelated game selections when staged. The user explicitly chooses or confirms the Minecraft instance at install time.
- `.mrpack` import, loader installation, arbitrary custom Minecraft launchers, unmanaged dependency detection, and automatic dependency downloading are **not** implemented; these remain download-only or review-blocked.
- Nexus OAuth 2.0/PKCE remains development-only awaiting official client registration and live endpoint confirmation. No public sign-in or Nexus download approval is claimed.
