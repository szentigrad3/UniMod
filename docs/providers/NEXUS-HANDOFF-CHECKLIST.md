# Nexus Mods registration handoff — UniMod v0.53

**Current as of 22 October 2026, ticket #273059.**

Nexus Mods Support (Dominic) requested confirmation against their Acceptable Use Policy, selection of API integration method and a development build implementing the base framework. UniMod proposes **OAuth 2.0 with PKCE for desktop sign-in**, **official REST API for authenticated mod/file queries and eligible downloads**. GraphQL is optional for read-only metadata. Legacy WebSocket SSO and personal API-key developer testing remain separate, and are not the proposed public sign-in method.

For the full policy self-audit, implemented framework, outstanding requests, and test commands, see **NEXUS-REVIEW-2026-10-22.md**.

Status: registration not approved; OAuth client ID, approved redirects, scopes, authorize/token endpoints, preferred REST API version and live download policy confirmation still required. Do not call this production OAuth support until Nexus confirms the details and real account/download tests pass.
