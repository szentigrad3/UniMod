# UniMod v0.45 — Source Lookup Reliability

## Changes
- Successful SMAPI catalogue lookups that provide **no Nexus match** are cached for 7 days per SMAPI UniqueID, installed version and manifest update keys. This avoids repeatedly hitting an incomplete community catalogue during normal Check connected sources operations.
- Explicit **Identify mod sources automatically** bypasses the negative cache for a fresh check.
- API/network failures and per-mod API errors never become negative matches. A changed version or update key also triggers a fresh automatic lookup.
- The Updates screen now explains skipped, recently unmatched identities rather than silently reporting another zero-match result.
- Cache stores only an identity key, a hashed fingerprint and a timestamp. It never stores game paths, filenames, update keys, tokens or credentials.
- Existing positive source matches, manually assigned links, Nexus authentication, download approvals, SMAPI/BepInEx detection and backups are unchanged.

## Compatibility and scope
This is an API-usage and reliability update, not a comprehensive online Nexus catalogue. It does **not** identify every missing source, download mods, or imply Nexus registration has been approved. The SMAPI endpoint is unofficial and may change. A successful empty lookup is not evidence the mod isn't on Nexus.

## Testing
`python -m unittest discover -p 'test_*.py' -q` includes six new cache tests. For graphical checks use `xvfb-run -a python gui_source_lookup_smoke_v044.py` and `xvfb-run -a python gui_updates_smoke_v040.py`.
