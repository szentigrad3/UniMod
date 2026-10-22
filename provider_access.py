"""Provider access requirements for UniMod. No secrets are stored or sent."""

ACCESS = {
    'Nexus Mods': {
        'status': 'Public metadata works. OAuth sign-in and protected downloads require an approved app/client registration.',
        'next': 'Continue the existing support conversation; request an approved OAuth client ID, permitted redirect URI and download-policy guidance.',
        'url': 'https://help.nexusmods.com/article/114-api-acceptable-use-policy',
    },
    'CurseForge': {
        'status': 'Read-only API browsing requires a developer-approved API key. Downloads remain disabled in UniMod.',
        'next': 'Apply through the official CurseForge API key process and accept the third-party developer terms.',
        'url': 'https://support.curseforge.com/support/solutions/articles/9000208346-about-the-curseforge-api-and-how-to-apply-for-a-key',
    },
    'mod.io': {
        'status': 'mod.io read-only browsing uses a user-issued API key and your unique user API path.',
        'next': 'Generate a fresh key and enter it locally together with your User ID (from u-{id}.modapi.io/v1) and your desired Game ID. Verify the game before searching.',
        'url': 'https://docs.mod.io/restapi/introduction',
    },
    'Modrinth': {
        'status': 'Current public Modrinth metadata and approved CDN flows need no account key.',
        'next': 'Continue testing downloads and imported modpacks with disposable Minecraft instances.',
        'url': 'https://docs.modrinth.com/',
    },
}

def access_info(provider, *, key_present=False):
    info=ACCESS.get(provider)
    if not info:
        return {'status':'No account key is required for the currently implemented read-only catalogue action.',
                'next':'Continue using source review and staged downloads where supported.',
                'url':None, 'key':'Not used here'}
    return {**info,'key': ('Session key entered; provider approval still required for protected operations.' if key_present else
                            'No session key entered.')}
