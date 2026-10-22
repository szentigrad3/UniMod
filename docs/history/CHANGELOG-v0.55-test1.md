# UniMod 0.55 test1 — reviewed dependency workflow

**Test build, not a stable release.** Based on the complete v0.54 source archive.

- Added read-only recursive resolution of required Modrinth dependencies for a selected staged JAR and Prism/MultiMC profile. Version and loader filtering, exact pinned versions, circular chains, incompatible records, unsafe metadata, ambiguous releases, missing hashes and conflicting versions fail closed.
- Added user approval of each missing dependency and total download size **before downloads or game writes**. All required JARs download from the validated Modrinth CDN and are checked against publisher SHA-512. Each managed staged file retains a locally calculated SHA-256 receipt, as in v0.54.
- Added dependency-ordered reviewed installation with recovery of successfully written managed JARs if a subsequent install fails. Failure during downloading leaves the Minecraft profile untouched. Previously managed files still require hash verification and retain recovery copies on successful updates. A failed rollback requiring manual attention is reported explicitly.
- Added read-only `.mrpack` manifest inspector: checks archive checksum, ZIP member paths/symlinks, bounded expansion, manifest format, loader metadata, hashes, download origins and path collisions. It **does not** install modpacks or overrides yet.
- Fixed stale AppImage build identifiers (`0.52`), GitHub Actions artifact identifiers (`0.53`) and explicitly bundled the Minecraft, Modrinth dependency, Modrinth pack inspector and Nexus OAuth modules.
- Repaired obsolete GUI smoke-test assertions that still expected legacy navigation/layout structure; included current Minecraft smoke checks in CI.
- Nexus OAuth 2.0/PKCE remains **approval-gated** pending formal Nexus Mods client registration. No approved public Nexus auth/download access is claimed.

## Known limitations

- Actual Prism/MultiMC installations and live Modrinth downloads have not been exercised on the user's CachyOS machine. Network/provider failure and many collision/security paths are covered by mocked tests only.
- `.mrpack` import is **not implemented**. Review is inspection only; no automatic modpack extraction, downloads or config changes.
- CurseForge still requires an approved API key for read-only discovery; no new CurseForge installation method in this test build.
- Multi-project dependency installs are not a general mod-conflict solver. Existing manually installed JARs without UniMod receipts remain unverified; incompatible metadata is refused.
- No prebuilt AppImage is included in this source test artifact. The included corrected build script and CI workflow can produce one in a compatible Linux packaging environment with PyInstaller and appimagetool.
