# Existing profiles — read-only import preview (development)

The `profile_import_preview` module reuses UniMod's established
`minecraft_profiles.discover_instances` scanner to locate recognized
Prism Launcher and MultiMC instances on Linux. It inventories top-level
`.jar` and `.jar.disabled` files without opening archives or following
symlink entries. The preview **does not import or modify anything**.

This first milestone intentionally does not claim Gale/r2modman support.
Their on-disk profile formats and supported import semantics must be
independently verified before adding them. No conversion or deployment
action is exposed to users by this milestone.

The function returns internal instance paths for future selection UI.
`safe_summary` exports only totals (not paths or mod names). JAR counts
do not establish plugin IDs, provenance, compatibility or launch safety.

Development check:

```bash
python3 -m unittest -q test_profile_import_preview_v056.py
```

Next: reviewable source/destination mapping in GUI; conflict preflight;
atomic backups and rollback validation before enabling any import.
