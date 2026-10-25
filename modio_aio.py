"""Safe all-in-one mod.io tester: temporary files and metadata only.

Runs the existing isolated lifecycle self-test, verifies an explicit game and
mod via the official read-only API, and optionally downloads one small ZIP to a
temporary folder for integrity checking. Never stages or installs anything.
"""
import re

import modio_diagnostics
import modio_files
import modio_live_probe
import modio_selftest
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
              'reason': 'none', 'verified_bytes': 0}
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
    if (not isinstance(game_id, str) or not isinstance(user_id, str) or
            not re.fullmatch(r'[1-9][0-9]{0,11}', game_id) or
            not re.fullmatch(r'[1-9][0-9]{0,11}', user_id) or
            not isinstance(api_key, str) or len(api_key.strip()) < 8):
        report['reason'] = 'connect'
        return report

    _emit(progress, 'game')
    try:
        record = catalogue.modio_game(game_id, api_key, user_id=user_id, fetch=fetch)
        if _normal(record.get('name')) != _normal(game['name']):
            report['game'] = 'Failed'
            report['reason'] = 'wrong_game'
            return report
        report['game'] = 'Passed'
    except Exception:
        report['game'] = 'Failed'
        report['reason'] = 'game_api'
        return report

    if not isinstance(mod_id, str) or not re.fullmatch(r'[1-9][0-9]{0,11}', mod_id):
        report['reason'] = 'choose_mod'
        return report

    _emit(progress, 'metadata')
    try:
        identity = game_id + '/' + mod_id
        rows = modio_files.list_modfiles(identity, user_id=user_id, api_key=api_key, fetch=fetch)
        if not rows:
            report['metadata'] = 'Passed'
            report['reason'] = 'no_eligible_zip'
            return report
        # The exact file refresh also validates that the file has not changed.
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
    'connect': 'Enter your mod.io Game ID, API-path User ID and private key once.',
    'wrong_game': 'The mod.io game does not match your selected installed game.',
    'game_api': 'Game verification failed. Check your connection and credentials.',
    'choose_mod': 'Select a mod, or enter its numeric mod.io ID, to test a download.',
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
            'Result: ' + HELP[reason] + '\n'
            'Real-game installation: Not attempted\n'
            'Private key, account IDs, mod IDs, paths and download URLs: excluded.\n')
