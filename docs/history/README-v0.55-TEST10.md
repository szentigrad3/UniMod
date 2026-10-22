# UniMod v0.55 Test 10 — Linux tester guide

## Launch

```bash
chmod +x UniMod-0.55-test10-x86_64.AppImage
./UniMod-0.55-test10-x86_64.AppImage
```

This file is an experimental bundled, self-extracting **Linux ELF**, not a standard AppImageKit Type 2 image. Requires compatible glibc, graphical desktop and `tar`. The source includes the separate official AppImageKit GitHub Actions builder.

## Review Graveyard Keeper / Graveyard Keeper 2 source candidates

1. Select the correct game and scan installed BepInEx mods.
2. Open Tools → Source Matching, select a mod, click **Find candidate pages…** or **Search without Nexus ZIP…**.
3. Search the public Nexus Mods catalogue. Results are ordered by *title-search relevance*, not match confidence. A matching title never proves the installed DLL comes from that page.
4. Open the exact official page; check game, author/uploader, version and intended DLL contents. Only then approve a source link in UniMod. No automatic installation occurs.
5. For stronger evidence, use local ZIP + `.meta` SHA-256 matching from Test 8. Even this must be reviewed because local sidecars are not provider-authenticated.

In the Mod Websites tab, choose a provider and click **Provider access requirements…** for the official registration/key instructions.

## Provider access boundary

- **Nexus Mods:** metadata browsing works without login. Public-facing OAuth and protected file downloads require official client registration. The support conversation is pending; never ship somebody else's client ID.
- **CurseForge:** an approved API key is required. Test 10 supports verified game IDs and read-only files; downloading is deliberately disabled pending approved provider authorization and implementation of its policy-compliant download flow.
- **mod.io:** requires your mod.io-issued user/game API key for REST requests.
- **Modrinth / GitHub / Thunderstore:** continue public discovery and approved download workflows, with install review. Live network, compatibility and native CachyOS installation are not established by offline tests.

Do not send API keys via chat or include them in diagnostics. UniMod's provider fields are session-only.

## Local tests

```bash
python3 -m unittest discover -p 'test_*.py' -q
xvfb-run -a python3 gui_candidate_review_smoke_v055.py
xvfb-run -a python3 gui_bepinex_search_hints_smoke_v055.py
xvfb-run -a python3 unimod.py --smoke-test
```
