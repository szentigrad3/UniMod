# UniMod privacy notes — development preview

UniMod is a locally running mod manager. It scans configured game folders and maintains local configuration under `~/.config/unimod/`. It can connect directly to official mod-provider services to check updates or request explicitly selected mod files.

- **Nexus credentials**: private-test API keys and post-registration SSO-returned user keys live only in memory. They are not persisted, transferred to any UniMod-operated backend, recorded in diagnostic reports, or intentionally printed to logs.
- **SSO**: after the application is officially registered, a user's system browser is opened to Nexus Mods to authorise the application. Authentication communication occurs directly with Nexus Mods over encrypted connections.
- **Mod inventory**: folder names, manifest IDs, versions and source associations are stored locally for source recognition. No UniMod telemetry server is implemented.
- **Downloads**: a user must select/approve a remote file, which is downloaded into their existing Downloads folder. Downloads are not automatically installed.
- **Revocation**: clear the key using UniMod's button, quit UniMod, and/or revoke its API authorization in your Nexus Mods account.

This is a development privacy note, not an independent security assessment.

## Temporary NXM tokens (v0.37)
Official Nexus manager-download URLs may contain short-lived user-linked authorization parameters. UniMod holds these **in process memory only** and never writes full NXM URLs into a report or saved queue. Clicking an NXM link may temporarily expose its URL in a desktop process command line, as with many Linux desktop URL handlers. Avoid posting screenshots of terminal process listings or copying those links into public chats. Closing UniMod discards pending tokens; completed downloads discard them immediately.
