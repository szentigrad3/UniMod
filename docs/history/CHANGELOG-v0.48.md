# UniMod 0.48 — Automatic local download discovery

- **Find mod sources** now searches downloaded ZIP archives up to three nested directory levels inside the selected folder, instead of only inspecting top-level ZIP files.
- A default-on, opt-out checkbox searches recognised local download locations such as `~/Downloads`, `~/downloads`, `~/Download`, and UniMod's download folders. This is a *local read-only* scan; no Nexus API key or network request is required.
- Only explicitly selected or named download locations are searched. The scanner never recursively searches the entire home directory or game installation automatically. It does not follow symlinked directories or ZIP files.
- Scans are bounded to 500 directories, 180 recent ZIPs and 512 MiB per ZIP. The existing ZIP-manifest safety checks are retained.
- Existing MO2 sidecar metadata and UniMod Nexus download receipts now work with ZIPs found inside nested download folders. Exact SMAPI UniqueIDs are required for matching; filename-only page IDs remain reviewable suggestions, never trusted proof.
- Conflicting page IDs remain blocked from bulk assignment. No sources or mods are changed until the user reviews and confirms.
- No changes to public Nexus registration/authentication status. Official app SSO remains awaiting approval.

## Limitations

This update does **not** search Nexus by name or recover download identities for ZIPs which were deleted and lack any available receipt/update key. RAR/7z files are not scanned for SMAPI manifest identities (although the Nexus download queue can handle these archive formats). It cannot guarantee that all already-installed mods will be linked.

## Validation

Run `python3 -m unittest discover -p 'test*.py' -q`. The UI can be tested with `xvfb-run -a python3 gui_auto_archive_smoke_v048.py`. As before, the standalone Linux binary uses an experimental extract-and-run runtime rather than official AppImageKit tooling.
