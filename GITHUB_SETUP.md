# Publishing UniMod on GitHub

The repository's public maintainer is **@szentigrad3**. This package is a *source repository*, not a GitHub Release asset. The `0.55.0-test12` build is a **development preview**.

## Create the repository

1. Sign in to the GitHub account you want to own the project.
2. Create an **empty** repository named `UniMod` (no GitHub-generated README, .gitignore or licence; these are included here). It can be private for preflight review, then public when you're ready.
3. Extract the repository ZIP and open a terminal inside the extracted `UniMod` folder.
4. Using your own locally configured Git author identity, run:

   ```bash
   git init -b main
   git add .
   git commit -m "Initial UniMod development preview"
   git remote add origin https://github.com/szentigrad3/UniMod.git
   git push -u origin main
   ```

   Or, after `gh auth login`, run `gh repo create szentigrad3/UniMod --public --source=. --remote=origin --push` instead of creating an empty repository and manually adding the remote. Do not run both flows. GitHub authentication is handled by GitHub or the GitHub CLI; do not embed personal access tokens in remote URLs.

## Configure the repository

- About: `Linux-first mod manager for safe mod discovery, reviewed updates and recovery.`
- Topics: `linux`, `mod-manager`, `python`, `stardew-valley`, `minecraft`, `bepinex`, `modrinth`
- Default branch: `main`; enable branch protection or rulesets with required `Python CI` checks.
- Enable GitHub Issues, Discussions (optional), private vulnerability reporting, and Actions.
- Keep API credentials, downloaded mod ZIPs, user inventories and real game folders outside the repo.

## First GitHub release

1. Ensure CI has passed for the initial main branch.
2. Run manual `Linux AppImage build (release candidate)` workflow and inspect its **actual CI artifact**. The historical local self-extracting development build is not a verified Type 2 AppImage.
3. Complete [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).
4. If remaining checks are incomplete, create a GitHub **Pre-release** (not Latest stable) with tag `v0.55.0-test12`.
5. Attach verified CI artifact(s), checksum file and short notes from `CHANGELOG.md`; don't upload provider keys or signed download URLs.

## Working together on maintenance

Once this repository exists and is accessible through the connected GitHub account, ChatGPT can help inspect issues, review code and PRs, prepare patches, run tests and draft releases when asked. The human maintainer approves merges, credential use, externally visible communications and releases. Avoid pretending contributions came from other people or fabricating a history.
