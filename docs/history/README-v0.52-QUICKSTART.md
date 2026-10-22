# UniMod 0.52 — Provider Inbox quick start

1. Launch the executable and select a configured game using the game picker.
2. Open **Discover**. Search GitHub or Modrinth, choose a release, click **Browse release files…**, then **Download selected to inbox**. To stage Thunderstore packages, open **Thunderstore Search**, load the community catalogue, select a package, and click **Stage selected ZIP to Provider Inbox**.
3. Open **Provider Inbox** (a separate tab). Click **Refresh downloaded files**, select a staged archive, then **Review & install selected…**.
4. UniMod checks the downloaded file fingerprint, selected game, archive identities, installed packages and required dependencies. It blocks unsupported formats and unclear installs.
5. **Only** if preflight passes do you receive an explicit confirmation. Existing installed SMAPI/BepInEx mods use the backup-protected replacement path; new installs receive managed recovery receipts.

Compatibility: Modrinth Minecraft JAR/MRPACK/ZIP downloads are **download-only** until a proper Minecraft loader deployment backend exists. Some GitHub ZIPs and Thunderstore packages may not fit the selected game. Provider identity and a matching checksum are not a malware or gameplay compatibility guarantee.

Nexus public SSO still awaits its approved application slug and live validation; use `--nexus-readiness` to inspect the existing handoff status. No secret keys are stored in these receipts.
