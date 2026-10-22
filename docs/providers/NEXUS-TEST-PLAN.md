# UniMod v0.36 — Nexus review test plan

**Before Nexus registration:** use a *private testing key* from your Nexus account; never embed or attach that key to registration correspondence. The WebSocket sign-in button correctly explains that Nexus must issue an application slug first.

1. Launch the Linux source build: `python unimod.py` (requires Python 3 + Tkinter; for WebSocket SSO later, `websocket-client`).
2. Open **Nexus Updates**. Verify **Registration info** shows that SSO registration is pending.
3. Enter a personal development key (in a masked field); click **Test API connection**. It should authenticate via the Nexus v1 validation API without storing the key.
4. Select Stardew Valley and use **Check next 25**. Only exact verified IDs should be checked, duplicate components should share a request, and failures should stop on common authentication/network/rate-limit errors.
5. Select a linked mod, choose **Browse / download files…**, and verify file entries are shown from the real Nexus file API. The user must select the exact file.
6. For an authorised account, choose a test mod archive and confirm it is saved to the chosen Downloads folder, not installed. Duplicate names must be refused. The result should be reviewable in UniMod's Update Inbox.
7. For a free account, open the Nexus mod page in browser and choose its approved manager-download action; use **Import NXM download link…** if a link is supplied. Verify expired tokens are rejected and direct downloads cannot bypass account restrictions.
8. Confirm the `Clear key` button clears credentials for the current process and restarting UniMod does not recover them.
9. After Nexus issues an application slug: set `UNIMOD_NEXUS_APP_SLUG=<approved-slug>` in the launcher environment, click **Connect Nexus account**, approve UniMod in the browser, and verify that the session-only key is received, then test steps 3–8 again.

**Known limitations:** Live Nexus authentication, Premium downloads and registered SSO require external account/approval testing. Some authorised CDN mirrors may not be on the current allowlist; in that case UniMod refuses the link and asks users to download through the official browser rather than lowering transport restrictions. No background polling.
