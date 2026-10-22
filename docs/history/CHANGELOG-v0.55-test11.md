# UniMod v0.55 Test 11 — mod.io user API path and safety

- Support official `u-{user-id}.modapi.io/v1` accounts for read-only mod.io searches.
- Add a local User ID field and a game verification/consent step.
- Reject search results from unrelated game IDs, untrusted profile URLs, changed session keys, or changed game contexts.
- Require matching verified mod.io game title before linking a source to a locally installed mod.
- Preserve Nexus registration gate and CurseForge API key requirements; no provider keys in archives.
- All credentials stay only in the running GUI session, never in generated logs.

No live requests were made with the API key shown in a screenshot. Rotate any visible key before entering a new key locally.
