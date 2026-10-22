# UniMod — Nexus OAuth registration handoff (ticket #273059)

Prepared: 22 October 2026.  This is a **development-test build**, not a Nexus-approved public client.

## Decision and responsibilities

- **User sign-in:** OAuth 2.0 Authorization Code + S256 PKCE, subject to Nexus application registration. User confirms consent in their system browser; a bound IPv4 loopback redirect receives the authorization code. Never ask for account passwords or scrape cookies.
- **Mod metadata and authorized downloads:** Nexus REST API (existing v1 file/mod endpoint support for developer testing). Confirm with Nexus whether to use v1 or v3 for production downloads; the v3 download-link endpoint is currently marked Experimental in the published reference.
- **GraphQL v2:** Optional non-download metadata, not part of the initial authentication/download minimum.
- **Legacy WebSocket SSO:** Preserved behind Nexus-issued slug for backward compatibility; not the proposed public sign-in method.

## Implemented in v0.53 development build

`nexus_oauth.py`:
- Separate registered OAuth client ID, authorization endpoint, token endpoint and redirect URI. None are invented or embedded.
- URL validation for official HTTPS Nexus-hosted endpoints and loopback callback `http://127.0.0.1:<port>/callback`.
- Cryptographic verifier, RFC 7636 S256 challenge, random `state` and constant-time state comparison.
- One-use callback parser, no browser-code logging, failure redaction, token request/refresh and Bearer header helpers.
- Local-only HTTP callback server, blocked provider redirects on token POST, limited token payload, fixed read timeouts.
- Tokens are in memory only; approval must precede enabling production OAuth downloads. Existing Nexus API key dev path is independent.
- UI button for OAuth development login and an extended `--nexus-readiness` report.

**Not yet implemented or independently verified:** actual registered-client browser sign-in, live access-token validation against Nexus REST, real-world token refresh/revocation, provider-confirmed scopes, OAuth-driven download authorization, any persistent OS keyring storage, or compatibility with OAuth callbacks other than the registered loopback route. Do not call these completed.

## Policy review — https://help.nexusmods.com/article/114-api-acceptable-use-policy

| Requirement | v0.53 developer assessment |
| --- | --- |
| Register public client / submit test build | Contacted support; ticket #273059; development source/build prepared |
| Personal API keys only for development/personal use | Legacy key entry is session-only and labelled private developer testing; public sign-in stays gated |
| Accurate Application-Name and Application-Version headers | Uses `UniMod` and `0.53.0`; regression-tested |
| Do not harvest or rehost API catalogue data | No bulk scrape/rehost workflow in Nexus integration; exact linked mod IDs only, batch bounded; still requires Nexus's review |
| No server-side credential storage or unattended credential access | No UniMod-hosted credential service; OAuth token data is process-memory-only; no unattended background polling of Nexus accounts |
| Download access restrictions | Browser-provided NXM key/expiry retained; no deliberate restriction bypass; live free/Premium checks pending |
| User-directed actions / rate limits | User-initiated request and bounded check batches; need Nexus to verify final limits |

The above is a *self-assessment*, not a Nexus compliance certification.

## Request to Nexus Support

1. Confirm whether OAuth Authorization Code with PKCE is the recommended approach for an open-source Linux desktop client.
2. Issue an OAuth public client ID, or supply the registration steps; confirm supported authorization and token endpoint URLs.
3. Confirm supported loopback callback registration `http://127.0.0.1:8765/callback` (or specify a preferred custom scheme), callback port policy, and scopes.
4. Confirm the recommended REST API version/endpoint for mod metadata, file listing, free-user NXM keys, Premium authorizations, rate limits and restrictions.
5. Identify any changes Nexus wants to the linked development AppImage/source and privacy practices before approval.

Do not send authorization codes, user API keys, access tokens, refresh tokens, cookies, or private downloads to support.

## Local developer verification

```sh
./UniMod-0.53-Nexus-PKCE-Dev-x86_64.AppImage --nexus-readiness
./UniMod-0.53-Nexus-PKCE-Dev-x86_64.AppImage --smoke-test
```

After Nexus supplies approved settings:

```sh
UNIMOD_NEXUS_OAUTH_CLIENT_ID='<issued-client-id>' \
UNIMOD_NEXUS_OAUTH_AUTHORIZE_URL='<confirmed-https-authorize-URL>' \
UNIMOD_NEXUS_OAUTH_TOKEN_URL='<confirmed-https-token-URL>' \
UNIMOD_NEXUS_OAUTH_REDIRECT_URI='http://127.0.0.1:8765/callback' \
  ./UniMod-0.53-Nexus-PKCE-Dev-x86_64.AppImage
```

These are developer configuration inputs, not secrets to send through a chat. The callback must be registered with Nexus before testing. The OAuth client does not yet route downloaded files through OAuth; legacy testing path remains independent until that work is approved and verified.
