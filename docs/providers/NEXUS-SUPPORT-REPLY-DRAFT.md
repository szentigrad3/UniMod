# Draft reply to Dominic — Nexus Mods API registration #273059

Hi Dominic,

Thank you for the guidance. I've reviewed the Nexus Mods API Acceptable Use Policy and have prepared an updated UniMod development build for your review.

UniMod is an open-source Linux desktop mod manager. Our planned approach is **OAuth 2.0 Authorization Code with PKCE** for user-initiated browser authentication, combined with the official **REST API** for mod/file metadata and authorized downloads. We will respect user/account download eligibility, NXM browser approvals where required, and API limits. GraphQL may be used later for metadata but is not required for the core download workflow.

The development build now includes a PKCE S256 verifier/challenge, random state validation, localhost callback, code/token exchange, refresh-token support and tests. Credentials remain in memory; the workflow remains disabled until official client registration details are supplied. Our existing REST v1 file selection and user-reviewed download flow works separately with personal API keys for private developer testing only. We do not host or harvest Nexus content or run an unattended download service.

Could you confirm:

1. The steps to issue an OAuth public client ID for UniMod, along with the current authorization and token endpoints and supported scopes;
2. Whether `http://127.0.0.1:8765/callback` is acceptable for an installed Linux desktop app (or if a custom scheme is preferred);
3. Whether Nexus recommends REST v1 or v3 for authenticated download links and file metadata, including how free/Premium account restrictions should be handled;
4. Any changes to the development client or additional materials you'd like before registration can proceed.

I can provide the v0.53 development AppImage, complete MIT-licensed source, application logo, API test plan and privacy/policy review. I appreciate your assistance and will follow the recommended integration route.

Kind regards,
Jason
