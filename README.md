# UniMod

A Linux-first desktop mod manager for discovering existing game mods, reviewing updates and safely applying supported mod packages.

**Latest public release:** `v0.55.0-test12` (development preview). The `main` branch contains **unreleased v0.56 features**. Neither is a stable release. Maintained by [@szentigrad3](https://github.com/szentigrad3). Code is MIT-licensed; bundled dependencies retain their own licences.

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

**Linux binaries:** The public development pre-release has a standard AppImage built and smoke-tested by GitHub Actions. The latest unreleased `main` features are available from source until a new AppImage is built and verified. See the [AppImage workflow](.github/workflows/appimage.yml).

## New tester? Start here (v0.56 development)

From the current source directory, run `python3 unimod.py`, select **Discover**, and click **Help me test mod.io…**. The guide shows the next step and links directly to each relevant screen.

1. Choose a supported installed game, select **mod.io**, and enter its game ID, your mod.io account API-path ID, and your personal API key **inside UniMod only**.
2. Verify the game name, search for one mod, and run the read-only API check.
3. Open the release files and use **Test download (temporary)** on a ZIP up to 64 MiB. This fetches, verifies, then deletes a temporary ZIP without installing anything.
4. For a real install, stage a separate reviewed ZIP and inspect it in **Provider Inbox**. Installation always needs confirmation and is available only for supported layouts.

The guide also has a **Run built-in safety test** button. It checks a disposable fake game's download, installation, update and rollback **without using your API key, a terminal or your real game files**. The guide shows Pass/Fail and includes it in the **Copy safe test report** output for bug reports. It never includes API keys, local paths, mod/account IDs or signed download URLs. A reported pass is tied to the current game, mod and key session. An offline self-test is also available with `python3 unimod.py --modio-self-test`, but it does not replace the live check.

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
