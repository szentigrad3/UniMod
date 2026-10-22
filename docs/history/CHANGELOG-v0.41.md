# UniMod v0.41 — Updates-to-install handoff

- The unified Updates screen now has **Find downloaded updates** and **Review & Install selected** actions.
- Exact SMAPI UniqueIDs or BepInEx package metadata associate local downloaded ZIPs with installed mods. Similar names, ZIP filenames and shared Nexus pages are *never* considered sufficient evidence for installation.
- One uniquely matched update ZIP appears directly in Updates as **Ready for review**; ambiguous multi-ZIP matches must be resolved in Update Inbox.
- A confirmation dialog shows installed/new versions, archive name, provenance warning, and a read-only SMAPI dependency comparison (only *new* required-dependency concerns are highlighted).
- Approved installations use the existing revalidation, recovery backup and rollback functions; already-installed files are not changed without confirmation.
- Following successful installation, cached version-check results are cleared rather than incorrectly showing pre-update results.
- Download batch completion requests a fresh ZIP inventory scan, without automatically installing anything.
- SMAPI ZIP parser now accepts non-lowercase manifest filenames and JSON5-style manifests (matching the installed-folder scanner).
- SMAPI ZIPs are fingerprinted on scan and rechecked at installation, preventing silent replacement of a ZIP with altered content but the same mod ID/version.

## Limitations

- ZIP only for reviewed installation. Nexus download queue may accept 7z/RAR, but the reviewed update scanner deliberately does not apply them.
- Nexus public SSO still requires approval and an application identifier from Nexus Mods. No registration approval is claimed.
- SMAPI dependency inspection is advisory, not a compatibility guarantee. BepInEx dependency compatibility is not yet assessed.
- Unknown source identity, ambiguous ZIP ownership, or multi-mod packs still require manual review.
- Downloads are not verified as authentic merely by having a matching mod ID.
- The experimental standalone executable uses a custom extract-and-run AppImage runtime.
