# UniMod — Comparative Mod Manager Research and UX Roadmap

Research date: **25 October 2026**. Based on documented public features; implementation priorities are specific to UniMod's existing Linux/Python/GTK? **Tkinter** architecture. This is a product study, **not source code copied from other mod managers**.

## Research findings

| Project | Verified pattern | What UniMod should learn | Reference |
| --- | --- | --- | --- |
| **Vortex** | Multi-game integrations, independent profiles, conflict-resolution workflows, Nexus updates | Bring profiles + conflicts + providers together into a single game-centered view | https://www.nexusmods.com/site/about/vortex |
| **Mod Organizer 2** | Mod isolation for reliable install and uninstall | Prefer reversible deployment with accurate provenance over writing directly to game roots | https://github.com/ModOrganizer2/modorganizer |
| **Prism Launcher** | Minecraft instances and version/loader-scoped Modrinth/CurseForge downloads | Treat each Minecraft instance as a separate profile; never suggest files incompatible with version/loader | https://www.prismlauncher.org/wiki/getting-started/download-mods/ |
| **Gale** | One-click imports from r2modman/Thunderstore, mod profiles, config editing, shared profile formats, link-based storage | Adopt existing profiles rather than forcing reinstall; make import review explicit and reversible | https://github.com/Kesomannen/gale/wiki/Features |
| **r2modman** | Enable/disable, updates and portable shareable profiles | Simple default actions and safe optional advanced screens | https://github.com/ebkr/r2modmanPlus |
| **CKAN** | Metadata-defined dependency, recommendation, conflict and version constraints | Move from optional hints to typed rules with strong incompatible-install refusal (where trusted metadata exists) | https://github.com/KSP-CKAN/CKAN/blob/master/Spec.md |
| **Limo** | Linux-native staging and deployment, Steam discovery, filename-case handling, backup tools | Keep deployment reversible, detect case-only collisions and give existing installations first-class treatment | https://github.com/limo-app/limo |
| **Amethyst** | Native Linux and Proton tooling, MO2-like staging and profiles | Focus on Linux paths, games launched through Proton and transparent per-game mod layout detection | https://github.com/Counterpart21/Amethyst-Mod-Manager |

## What UniMod already has

- Game discovery, including additional Steam libraries; SMAPI, BepInEx and Minecraft instance awareness.
- Read-only SMAPI dependency inspection and duplicate UniqueID detection.
- Local source matching, provider catalogues and file checksums.
- An explicit reviewed install workflow with backups and rollback, plus a disposable offline lifecycle test.
- Profiles and imported packages, plus mod.io key-only/advanced metadata/download diagnostics.
- V0.56 AIO mod.io tester, but mod.io does not list every UniMod-supported game.

**Problem: the user must visit many advanced tabs to discover these capabilities.**

## Ordered development plan

### P0 — Clarity and trust (start now)

1. **Check My Mods** on the main toolbar. Rescan selected game, reuse installed-mod and dependency audits, display plain-English counts and links to details, copy a redacted support report. No file writes. *Implemented in this PR.*
2. **Unified game Home**: show game name, recognized mod format, installed/enabled counts, warnings and three ordinary choices: **Check My Mods**, **Find Mods**, **Play**. Keep raw diagnostics under Tools.
3. **AIO provider test** must distinguish provider authentication, unsupported selected games, metadata, and download integrity. Never claim a public ZIP from a different game proves compatibility.

### P1 — Existing installations first

4. **Import from other managers**: detect r2modman, Gale and Prism/MultiMC profiles read-only; compare what exists before offering a migration. Never overwrite live profiles on detection alone.
5. **Unmanaged mod onboarding**: inventory existing SMAPI folders and BepInEx DLLs; present candidate provenance as *unverified* until matched to trusted IDs.
6. **Duplicate/collision warnings**: use exact mod IDs where available and warn about case-only path collisions on Linux.

### P2 — Installation safety and consistency

7. **Typed dependency rules** (CKAN-style) with explicit *required*, *recommended*, *conflicts* and *incompatible game version*. Only trusted provider metadata can trigger an installation block; speculative identity matching is advisory.
8. **Profile snapshots**: capture source-ID provenance, versions, enable/disable state and config diffs; test restore before making it one-click.
9. **Queued actions**: plan download and update transactions, show space requirements, and require one human confirmation to apply the reviewed plan. Keep rollback available.

### P3 — Cross-provider usability

10. **Unified updates** based on verified source identity, distinguishing newer evidence from availability and compatibility.
11. **Mod.io OAuth vs API key**: keep one credential field, validate bearer tokens via approved read-only API endpoints; never infer the account's unique API path from an API key. No unauthorized account changes.
12. **Nexus**: respect official registration and authentication/terms requirements; no workaround for protected downloads.

## Design rules

- Default to *game selection → My Mods → Find/Update → Play*.
- No extra API-ID questions when a safe supported discovery route can supply the identity. If information cannot be recovered, show a useful limitation instead of guessing.
- Every potentially destructive action must show exactly which files will change, provide an optional backup and require confirmation.
- Offline tests are not evidence of production-provider success; label results accurately.
- No raw API keys, OAuth tokens, signed download URLs, filesystem paths or personal IDs in copyable reports.
- Discover and import existing profiles **before** suggesting reinstall.
- Avoid copying GPL-licensed implementation code into UniMod's MIT repository without a deliberate license review. Borrow high-level product patterns, author independent code and preserve third-party attribution.

## Acceptance checks for the first improvement

- Check My Mods must not write to games, installs, or provider history.
- Correctly distinguish SMAPI dependency warnings from BepInEx limitations.
- Copyable report contains only aggregate counts and whitelisted statuses.
- A selected-game change cannot reuse stale scan results.
- Existing full Python test suite and Xvfb GUI regression must pass.

_References describe features from source project websites and repositories; rankings above are UniMod design recommendations, not claims that the other projects implement an identical workflow._
