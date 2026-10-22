# UniMod 0.38

- Forward official NXM deep links into one already-running UniMod window using per-user AF_UNIX IPC and peer credential checks.
- Secure single-instance lock, no disk writes of NXM keys, lock-socket owner-only permissions, duplicate link refresh.
- Explicit **Download all ready…** batch with sequential downloads, per-file results, error review and unchanged separate install approval.
- New **Clear finished** action; multi-select removal of queued requests.
- Hide private developer API key behind advanced account options; browser SSO still gated by Nexus registration.
- Keep existing game scanners, SMAPI component grouping, backups, file signatures and safe download checks.
- Test real forwarding, failure rejection and GUI batch workflow, including legacy regression tests.

This is a development release; the Nexus application registration and real SSO remain outstanding.
