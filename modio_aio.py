"""Safe all-in-one mod.io tester: temporary files and metadata only.

Runs the existing isolated lifecycle self-test, verifies an explicit game and
mod via the official read-only API, and optionally downloads one small ZIP to a
temporary folder for integrity checking. Never stages or installs anything.
"""
import re
from urllib.parse import urlencode

import modio_diagnostics
import modio_files
import modio_live_probe
import modio_selftest
import modio_keyonly
import provider_catalogues as catalogue

RESULTS = ('Passed', 'Failed', 'Not tested')
REQUIRED = ('installed', 'updated', 'backups', 'tamper_refused',
            'wrong_game_refused', 'bad_download_refused',
            'failed_update_restored', 'secrets_not_persisted')


def _normal(value):
    return re.sub('[^a-z0-9]', '', str(value or '').casefold())


def _emit(callback, name):
    if callback is not None:
        callback(name)


def run_aio(game, *, game_id='', user_id='', api_key='', mod_id='',
            allow_transfer=False, fetch=None, opener=None,
            offline_run=None, progress=None, temp_parent=None):
    """Return only whitelisted status codes; omit credentials, IDs and URLs.

    Calls are sequential. Any error is reduced to a safe stage-specific code.
    No exception body or remote metadata is copied to the report.
    """
    report = {'offline': 'Not tested', 'game': 'Not tested',
              'metadata': 'Not tested', 'download': 'Not tested',
              'reason': 'none', 'verified_bytes': 0, 'selection': 'Not selected'}
    _emit(progress, 'offline')
    try:
        outcome = (offline_run or modio_selftest.run)()
        report['offline'] = ('Passed' if isinstance(outcome, dict)
                             and all(outcome.get(k) == 1 for k in REQUIRED) else 'Failed')
    except Exception:
        report['offline'] = 'Failed'

    if not isinstance(game, dict) or game.get('kind') not in ('smapi', 'bepinex') or not _normal(game.get('name')):
        report['reason'] = 'choose_game'
        return report
    if not isinstance(api_key,str) or len(api_key.strip()) < 8:
        report['reason'] = 'connect'
        return report
    legacy = (isinstance(game_id,str) and isinstance(user_id,str) and
              re.fullmatch(r'[1-9][0-9]{0,11}',game_id) and
              re.fullmatch(r'[1-9][0-9]{0,11}',user_id))
    # Explicit but malformed legacy account IDs are never silently ignored.
    if (game_id or user_id) and not legacy:
        report['reason'] = 'connect'
        return report
    _emit(progress, 'game')
    try:
        if legacy:
            record = catalogue.modio_game(game_id, api_key, user_id=user_id, fetch=fetch)
            if _normal(record.get('name')) != _normal(game['name']):
                report['game'] = 'Failed'
                report['reason'] = 'wrong_game'
                return report
        else:
            # The key cannot reveal the owner's user ID. Resolve an exact
            # public game name; never guess a game from the API key.
            game_id = modio_keyonly.resolve_game(game, api_key, fetch=fetch)
            user_id = None  # Public key-only GET route, not /me.
        report['game'] = 'Passed'
    except modio_keyonly.ResolutionError as exc:
        report['game'] = 'Failed'
        report['reason'] = str(exc) if str(exc) in HELP else 'game_api'
        return report
    except Exception:
        report['game'] = 'Failed'
        report['reason'] = 'game_api'
        return report

    _emit(progress, 'metadata')
    try:
        selected = isinstance(mod_id, str) and re.fullmatch(r'[1-9][0-9]{0,11}', mod_id)
        rows = []
        if selected:
            identity = game_id + '/' + mod_id
            report['selection'] = 'Selected mod'
            rows = modio_files.list_modfiles(identity, user_id=user_id, api_key=api_key, fetch=fetch)
        elif allow_transfer:
            # An explicitly approved, temporary-only test may use one public
            # release from the verified game. Never auto-install that ZIP.
            base = modio_files._base(user_id, api_key)
            address = f'{base}/games/{game_id}/mods?' + urlencode({
                'api_key': api_key.strip(), '_limit': 20})
            page = catalogue.fetch_json(address, fetch=fetch)
            if not isinstance(page, dict) or not isinstance(page.get('data'), list):
                raise ValueError('Invalid mod listing')
            for mod in page['data'][:8]:
                if not isinstance(mod, dict) or (mod.get('game_id') is not None
                    and str(mod['game_id']) != game_id):
                    continue
                proposed = str(mod.get('id') or '')
                if not re.fullmatch(r'[1-9][0-9]{0,11}', proposed):
                    continue
                candidate = modio_files.list_modfiles(
                    game_id+'/'+proposed, user_id=user_id, api_key=api_key, fetch=fetch)
                if any(type(r.get('size')) is int and
                       0 < r['size'] <= modio_live_probe.MAX_PROBE_BYTES for r in candidate):
                    identity,rows = game_id+'/'+proposed,candidate
                    report['selection'] = 'Automatic public test mod'
                    break
        else:
            report['reason'] = 'choose_mod'
            return report
        if not rows:
            report['metadata'] = 'Passed'
            report['reason'] = 'no_eligible_zip'
            return report
        # Verify exact identity and source metadata before any transfer.
        modio_files.refresh_selected(rows[0], user_id=user_id, api_key=api_key, fetch=fetch)
        report['metadata'] = 'Passed'
    except Exception:
        report['metadata'] = 'Failed'
        report['reason'] = 'metadata_api'
        return report

    eligible = [r for r in rows if type(r.get('size')) is int
                and 0 < r['size'] <= modio_live_probe.MAX_PROBE_BYTES]
    if not eligible:
        report['reason'] = 'zip_too_large'
        return report
    if not allow_transfer:
        report['reason'] = 'transfer_not_approved'
        return report

    # Choose the smallest eligible ZIP to minimise data usage. This is only a
    # temporary integrity test, not approval to install or a compatibility claim.
    item = min(eligible, key=lambda x: (x['size'], -int(x['version_id'])))
    _emit(progress, 'download')
    try:
        outcome = modio_live_probe.probe_download(
            item, user_id=user_id, api_key=api_key, fetch=fetch,
            opener=opener, temp_parent=temp_parent)
        if outcome.get('temporary') is not True or outcome.get('installed') is not False:
            raise ValueError('Unverified temporary transfer')
        report['download'] = 'Passed'
        report['verified_bytes'] = int(outcome.get('bytes_verified', 0))
        report['reason'] = 'complete'
    except Exception:
        report['download'] = 'Failed'
        report['reason'] = 'download_failed'
    return report


HELP = {
    'none': 'Ready.',
    'choose_game': 'Choose a supported game in UniMod, then run the test again.',
    'connect': 'Enter your private mod.io API key. Game selection is taken from UniMod.',
    'key_path_required': 'This key needs its unique mod.io API path. Key-only access was not accepted; no account ID was guessed.',
    'game_not_found': 'The selected game could not be matched exactly in mod.io’s public catalogue.',
    'ambiguous_game': 'Multiple or incomplete game matches: choose an unambiguous supported game before testing.',
    'wrong_game': 'The mod.io game does not match your selected installed game.',
    'game_api': 'Game verification failed. Check your connection and credentials.',
    'choose_mod': 'Select a mod, or approve an automatic public ZIP test.',
    'metadata_api': 'Mod release metadata could not be verified.',
    'no_eligible_zip': 'This mod has no eligible public ZIP to test.',
    'zip_too_large': 'No eligible ZIP is under the 64 MiB safety limit.',
    'transfer_not_approved': 'Temporary downloading was not approved; nothing was downloaded.',
    'download_failed': 'Temporary download failed verification. No game files changed.',
    'complete': 'Checks finished. The temporary ZIP was deleted; no game files changed.',
}


def public_report(result):
    """Safe human-readable report; whitelist statuses and reason codes only."""
    state = result if isinstance(result, dict) else {}
    def value(key):
        r = state.get(key)
        return r if r in RESULTS else 'Not tested'
    reason = state.get('reason')
    reason = reason if reason in HELP else 'none'
    return ('UniMod — Run All Tests (v0.56 development)\n'
            'Offline install/update/rollback: ' + value('offline') + '\n'
            'Official game verification: ' + value('game') + '\n'
            'Mod release metadata: ' + value('metadata') + '\n'
            'Temporary ZIP download: ' + value('download') + '\n'
            'Mod selection: ' + (state.get('selection') if state.get('selection') in
                ('Selected mod', 'Automatic public test mod') else 'Not selected') + '\n'
            'Result: ' + HELP[reason] + '\n'
            'Real-game installation: Not attempted\n'
            'Private key, account IDs, mod IDs, paths and download URLs: excluded.\n')
