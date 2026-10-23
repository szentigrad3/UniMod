"""Session-only, read-only live mod.io API diagnostics.

A diagnostic performs HTTPS GET requests for the chosen game, a selected mod's
releases, and at most one exact modfile. It never downloads mod bytes or writes
files. Its result contains no key, signed URL, local paths, or account identity.
"""
import modio_files
import provider_catalogues as catalogue


def check_modio_access(identity, *, user_id, api_key, fetch=None):
    """Return a small safe summary, never the source's signed URLs or API key."""
    game, mod = modio_files._identity(identity)
    # Game-name verification is independent of the selected mod's metadata.
    catalogue.modio_game(game, api_key, user_id=user_id, fetch=fetch)
    files = modio_files.list_modfiles(identity, user_id=user_id,
                                     api_key=api_key, fetch=fetch)
    if files:
        # Refresh a specific returned identity. The resulting signed URL stays
        # inside this call and is discarded; no archive data is requested.
        first = files[0]
        modio_files.refresh_selected(first, user_id=user_id,
                                     api_key=api_key, fetch=fetch)
        return {'status': 'Verified metadata access',
                'game_id': game, 'mod_id': mod,
                'eligible_zip_files': len(files),
                'exact_file_verified': True,
                'checked_file_id': first['version_id'],
                'downloaded': False}
    return {'status': 'Game and listing accessible; no eligible ZIP files',
            'game_id': game, 'mod_id': mod,
            'eligible_zip_files': 0,
            'exact_file_verified': False,
            'checked_file_id': '', 'downloaded': False}
