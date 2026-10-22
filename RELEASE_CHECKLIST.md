# Release checklist

A GitHub upload is not the same as a validated stable release.

- [ ] Ensure application name/version, docs and changelog describe the same build.
- [ ] Verify that no API keys, credentials, tokens, personal data, absolute machine paths or third-party mods are included.
- [ ] Confirm application icon/logo ownership and third-party licence notices.
- [ ] Run the Python regression suite and GUI smoke tests.
- [ ] Build a **standard** AppImage in the Linux GitHub Actions workflow, run its `--smoke-test` and download the CI artifact for inspection.
- [ ] Test on an actual Linux desktop (including CachyOS), using disposable SMAPI/BepInEx and Prism/MultiMC profiles.
- [ ] Test live provider metadata and download flows with your own private credentials (do not publish credentials or URLs containing tokens).
- [ ] Confirm Nexus, CurseForge and mod.io access follows the provider's current terms; disable features where approval is missing.
- [ ] Check safe rollback after failed downloads, tampered ZIPs, wrong-game matches and installation failures.
- [ ] Confirm the checksum file matches the exact files attached to the GitHub Release.
- [ ] Publish as a **pre-release** until live provider and distribution validation is complete.

Recommended first tag: `v0.55.0-test12` (GitHub Pre-release).
