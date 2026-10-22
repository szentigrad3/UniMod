# UniMod — external provider approvals still needed

## Nexus Mods

Continue the existing UniMod API registration ticket rather than creating a duplicate. As of the 22 October 2026 mailbox check, UniMod's latest reply was sent and no newer Nexus Support approval/registration email was found. Request an official OAuth client ID, approved redirect URI, permitted scopes and download restrictions. The experimental source and Linux executable can be shared with support on request.

Official: https://help.nexusmods.com/article/114-api-acceptable-use-policy

## CurseForge

The official process requires an API key application, developer terms and Overwolf review. Be prepared to provide an app name, source/release location, description, supported games, expected request volumes, content-author protection and privacy approach. Request scope/permissions for discovery, release metadata and staged user-initiated downloads. Do not commit a key into the source.

Official: https://support.curseforge.com/support/solutions/articles/9000208346-about-the-curseforge-api-and-how-to-apply-for-a-key

## mod.io

The account is known to have read-only API access enabled. If any screenshot displayed a key, rotate it. UniMod Test 11 accepts a replacement key only in its masked session field, and supports the account-specific `u-{user-id}.modapi.io/v1` URL. Use the local User ID + selected Game ID. Do not include any key in bug logs or release archives.

Official: https://docs.mod.io/restapi/introduction

## Key handling and testing

These are genuine external blockers. UniMod should not fake registration approval, bypass authenticated download restrictions, or silently route requests through an unapproved proxy. Until credentials/permissions are issued, all unsupported file operations remain disabled.
