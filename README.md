# UniMod

A Linux-first desktop mod manager for discovering existing game mods, reviewing updates and safely applying supported mod packages.

**Current status:** `0.55.0-test12` — public **development preview**, not a stable release. Maintained by [@szentigrad3](https://github.com/szentigrad3). Code is MIT-licensed; bundled dependencies retain their own licences.

UniMod is intended to make it easier to manage mods from different providers without bypassing creator permissions or provider download restrictions.

## Features

- Find installed Steam games and mod directories, including Stardew Valley SMAPI and supported BepInEx installations.
- Discover public releases and compare update candidates through Modrinth, GitHub, Thunderstore, and supported catalogue integrations.
- Inspect Minecraft Prism Launcher/MultiMC profiles, verify Modrinth versions and loaders, and review `.mrpack` imports.
- Review game-scoped downloads and locally install compatible SMAPI/BepInEx ZIPs with preflight checks, backup and rollback.
- Match existing Graveyard Keeper / Graveyard Keeper 2 BepInEx mods against downloaded archives or suggest review-only Nexus searches.
- Browse mod.io releases and stage supported, reviewed ZIP downloads using an API key entered locally by the user.

**Limits:** Not every game or mod format supports installation. Nexus account sign-in and protected downloads remain subject to official registration and account permissions. CurseForge downloading is not enabled. Mod.io download/update workflows have passed offline tests but have **not** been verified against a live user's account in this release.

## Get started (Linux)

Install Python 3.10+ and Tkinter using your distribution's package manager. Then run from the repository directory:

```bash
python3 unimod.py
```

On Arch/CachyOS, Tkinter is usually supplied by the system Python package. Optional integrations use Pillow, `tomli` for Python 3.10, and `websocket-client` as described in [`requirements-optional.txt`](requirements-optional.txt).

**Linux binaries:** Until a standard AppImage has passed the GitHub Actions build, the existing self-extracting `.AppImage`-named development binary should be treated as experimental. Do not present it as a verified AppImageKit Type 2 release. The [`build-appimage.sh`](build-appimage.sh) script and [AppImage workflow](.github/workflows/appimage.yml) define the intended standard build path.

## Safe installation model

Source search results are suggestions, not proof of authorship. UniMod does not automatically link uncertain results to installed DLLs, and it does not silently install updates. Supported install paths require a game/profile match, checks on archive paths, user review, and recovery backups where applicable. Only download mods that you trust and are entitled to use.

Provider API keys should **never** be committed, pasted into issue reports or submitted in screenshots. If a key is exposed, revoke it and create a new one. Local account keys are intended to be held only for the active session.

## Documentation

- [Current development notes](docs/history/README-v0.55-TEST12.md) and [change summary](CHANGELOG.md)
- [Provider status](PROVIDER-STATUS.md) and [privacy notes](PRIVACY.md)
- [How to contribute](CONTRIBUTING.md), [security reporting](SECURITY.md), and [licences](THIRD_PARTY_NOTICES.md)
- [GitHub publishing guide](GITHUB_SETUP.md), [release checks](RELEASE_CHECKLIST.md) and [previous development notes](docs/history/)

## Testing

```bash
python3 -m unittest discover -p 'test_*.py' -q
python3 -m compileall -q .
```

The current source baseline passes **518 offline tests**. This does not replace a real CachyOS GUI, provider API, or game-installation test.

## Maintenance and ownership

UniMod is an independent project maintained by **@szentigrad3**. Bug reports, feature requests and contributions are welcome through GitHub Issues and pull requests. Releases should be tagged and distributed only after the checks in [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) pass.

## Licence

UniMod's original source is licensed under the [MIT License](LICENSE). The vendored JSON5 package is Apache 2.0 licensed (see [`json5/LICENSE`](json5/LICENSE)). Game mods and external provider content are not bundled under the UniMod licence.
