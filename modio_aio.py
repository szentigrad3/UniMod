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

RESULTS = ('Passed', 'Failed', 'Not tested', 'Not available', 'Not verified')
REQUIRED = ('installed', 'updated', 'backups', 'tamper_refused',
            'wrong_game_refused', 'bad_download_refused',
            'failed_update_restored', 'secrets_not_persisted')


def validate_user_api_path(value):
    """Optional session-only user API endpoint; never guess or persist user IDs."""
    if value in ('',None):
        return None
    if not isinstance(value,str):
        raise ValueError('invalid_api_path')
    match=re.fullmatch(
        r'https://u-([1-9][0-9]{0,11})\\.modapi\\.io/v1/?',
        value.strip())
    if match is None:
        raise ValueError('invalid_api_path')
    return match.group(1)


def _normal(value):
    return re.sub('[^a-z0-9]', '', str(value or '').casefold())


def _emit(callback, name):
    if callback is not None:
        callback(name)



def _probe_issue(exc):
    """Map provider errors to fixed, non-secret outcomes; never emit URL or key."""
    if isinstance(exc,catalogue.ProviderError):
        reason=str(exc).casefold()
        if 'authentication' in reason or 'api access' in reason:
            return 'provider_api_access_required'
        if 'rate limit' in reason:
            return 'provider_rate_limited'
    return 'provider_request_failed'


def _probe_other_public_game(report, api_key, *, fetch=None, opener=None,
                             progress=None, temp_parent=None, account_id=None):
    """Bounded public ZIP check; keep each stage's reason without leaking IDs.

    A publicly accessible game catalogue DOES NOT establish access to modfile
    metadata. Failures at later read-only API steps must not masquerade as
    a genuine absence of public ZIPs.
    """
    report['scope']='Provider-only (different game)'
    report['probe_games']=0
    report['probe_mods']=0
    report['probe_file_lists']=0
    report['probe_stage']='game catalogue'
    seen_access=seen_limit=seen_error=False
    try:
        game_ids=modio_keyonly.public_test_game_ids(api_key,fetch=fetch,user_id=account_id)
    except modio_keyonly.ResolutionError as exc:
        report['reason']=('provider_api_path_required' if str(exc)=='key_path_required'
                          else 'provider_request_failed')
        return report
    except Exception:
        report['reason']='provider_request_failed'
        return report
    if not game_ids:
        report['reason']='provider_sample_unavailable'
        return report
    for public_gid in game_ids[:8]:
        report['probe_games']+=1
        report['probe_stage']='mod catalogue'
        try:
            base=modio_files._base(account_id,api_key)
            url=f'{base}/games/{public_gid}/mods?'+urlencode({
                'api_key':api_key.strip(),'_limit':12,'_sort':'-downloads_total'})
            page=catalogue.fetch_json(url,fetch=fetch)
            if not isinstance(page,dict) or not isinstance(page.get('data'),list):
                seen_error=True
                continue
        except Exception as exc:
            issue=_probe_issue(exc)
            seen_access |= issue=='provider_api_access_required'
            seen_limit |= issue=='provider_rate_limited'
            seen_error |= issue=='provider_request_failed'
            continue
        for item in page['data'][:5]:
            proposed=str(item.get('id') or '') if isinstance(item,dict) else ''
            if (not re.fullmatch(r'[1-9][0-9]{0,11}',proposed)
                    or (item.get('game_id') is not None
                        and str(item['game_id'])!=public_gid)):
                continue
            report['probe_mods']+=1
            report['probe_stage']='release files'
            try:
                rows=modio_files.list_modfiles(
                    public_gid+'/'+proposed,user_id=account_id,api_key=api_key,fetch=fetch)
                report['probe_file_lists']+=1
                eligible=[r for r in rows if type(r.get('size')) is int
                          and 0<r['size']<=modio_live_probe.MAX_PROBE_BYTES]
                if not eligible:
                    continue
                candidate=min(eligible,key=lambda r:(r['size'],-int(r['version_id'])))
                modio_files.refresh_selected(candidate,user_id=account_id,api_key=api_key,fetch=fetch)
            except Exception as exc:
                issue=_probe_issue(exc)
                seen_access |= issue=='provider_api_access_required'
                seen_limit |= issue=='provider_rate_limited'
                seen_error |= issue=='provider_request_failed'
                continue
            report['selection']='Independent public test mod'
            report['metadata']='Passed'
            _emit(progress,'download')
            report['probe_stage']='temporary ZIP'
            try:
                downloaded=modio_live_probe.probe_download(
                    candidate,user_id=account_id,api_key=api_key,fetch=fetch,
                    opener=opener,temp_parent=temp_parent)
                if (downloaded.get('temporary') is not True or
                        downloaded.get('installed') is not False):
                    raise ValueError('Unexpected download result')
                report['download']='Passed'
                report['verified_bytes']=int(downloaded.get('bytes_verified',0))
                report['reason']='provider_only_complete'
            except Exception:
                report['download']='Failed'
                report['reason']='provider_only_download_failed'
            return report
    if seen_access:
        report['reason']='provider_api_access_required'
    elif seen_limit:
        report['reason']='provider_rate_limited'
    elif seen_error:
        report['reason']='provider_request_failed'
    elif report['probe_file_lists']:
        report['reason']='provider_no_eligible_zip'
    else:
        report['reason']='provider_sample_unavailable'
    return report


def run_aio(game, *, game_id='', user_id='', api_key='', api_path='', mod_id='',
            allow_transfer=False, fetch=None, opener=None,
            offline_run=None, progress=None, temp_parent=None):
    """Return only whitelisted status codes; omit credentials, IDs and URLs.

    Calls are sequential. Any error is reduced to a safe stage-specific code.
    No exception body or remote metadata is copied to the report.
    """
    report = {'offline': 'Not tested', 'catalogue': 'Not tested',
              'game': 'Not tested', 'metadata': 'Not tested',
              'download': 'Not tested', 'scope': 'Not selected',
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
    try:
        account_id=validate_user_api_path(api_path)
    except ValueError:
        report['reason']='invalid_api_path'
        return report
    legacy = (isinstance(game_id,str) and isinstance(user_id,str) and
              re.fullmatch(r'[1-9][0-9]{0,11}',game_id) and
              re.fullmatch(r'[1-9][0-9]{0,11}',user_id))
    # Explicit but malformed legacy account IDs are never silently ignored.
    if ((game_id or user_id) and not legacy) or (legacy and account_id):
        report['reason'] = 'connect'
        return report
    _emit(progress, 'game')
    try:
        if legacy:
            record = catalogue.modio_game(game_id, api_key, user_id=user_id, fetch=fetch)
            report['catalogue']='Passed'
            if _normal(record.get('name')) != _normal(game['name']):
                report['game'] = 'Failed'
                report['reason'] = 'wrong_game'
                return report
        else:
            # The key cannot reveal the owner's user ID. Resolve an exact
            # public game name; never guess a game from the API key.
            game_id = modio_keyonly.resolve_game(game, api_key, fetch=fetch,
                                                  user_id=account_id)
            user_id = account_id  # User path, if provided; never call /me.
            report['catalogue']='Passed'
        report['game'] = 'Passed'
        report['scope']='Selected game'
    except modio_keyonly.ResolutionError as exc:
        code=str(exc)
        if code in ('game_not_found','ambiguous_game'):
            # The public API was reachable. The installed game is not
            # verifiably on mod.io, which does not invalidate API access.
            report['catalogue']='Passed'
            report['game']='Not available' if code=='game_not_found' else 'Not verified'
            report['metadata']='Not available'
            report['download']='Not available'
            report['reason']=code
            if allow_transfer and code=='game_not_found':
                return _probe_other_public_game(
                    report,api_key,fetch=fetch,opener=opener,
                    progress=progress,temp_parent=temp_parent,
                    account_id=account_id)
            return report
        report['game'] = 'Failed'
        report['reason'] = code if code in HELP else 'game_api'
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
    'game_not_found': 'No exact mod.io listing found for the selected game. Public catalogue access worked; this does not establish the key is invalid.',
    'ambiguous_game': 'Game match is ambiguous or incomplete. Public catalogue access worked, but this game was not verified.',
    'wrong_game': 'The mod.io game does not match your selected installed game.',
    'game_api': 'Game verification failed. Check your connection and credentials.',
    'choose_mod': 'Select a mod, or approve an automatic public ZIP test.',
    'metadata_api': 'Mod release metadata could not be verified.',
    'no_eligible_zip': 'This mod has no eligible public ZIP to test.',
    'zip_too_large': 'No eligible ZIP is under the 64 MiB safety limit.',
    'transfer_not_approved': 'Temporary downloading was not approved; nothing was downloaded.',
    'download_failed': 'Temporary download failed verification. No game files changed.',
    'complete': 'Selected-game checks finished. The temporary ZIP was deleted; no game files changed.',
    'provider_only_complete': 'Public mod.io ZIP verified using a different supported game. This does NOT test your installed game or verify account ownership.',
    'provider_only_download_failed': 'Independent public mod.io ZIP download failed. Your installed game was not touched.',
    'provider_sample_unavailable': 'Selected game is not on mod.io; the public sample had no verified release lists to test.',
    'provider_no_eligible_zip': 'Public mod listings were readable, but no ZIP passed the size, checksum and safety requirements.',
    'provider_api_path_required': 'The provider-only catalogue cannot be read using the legacy API address. Your mod.io account-specific API path may be required.',
    'provider_api_access_required': 'mod.io refused one or more mod/release requests. Public game catalogue access does not verify access to downloads; your account-specific API path may be required.',
    'provider_rate_limited': 'mod.io rate-limited the provider-only test. Try again later; this does not mean your API key is invalid.',
    'provider_request_failed': 'A provider-only API lookup failed. The public catalogue response alone cannot verify file/download access.',
    'invalid_api_path': 'Use the mod.io API URL from your own API dashboard (https://u-<your-user-id>.modapi.io/v1). No URL was saved.'
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
            'Public mod.io catalogue access: ' + value('catalogue') + '\n'
            'Official game verification: ' + value('game') + '\n'
            'Mod release metadata: ' + value('metadata') + '\n'
            'Temporary ZIP download: ' + value('download') + '\n'
            'Mod selection: ' + (state.get('selection') if state.get('selection') in
                ('Selected mod', 'Automatic public test mod', 'Independent public test mod') else 'Not selected') + '\n'
            'Test scope: ' + (state.get('scope') if state.get('scope') in
                ('Selected game', 'Provider-only (different game)') else 'Not selected') + '\n'
            'Result: ' + HELP[reason] + '\n'
            + ('Public sample: checked ' +
               str(max(0,min(8,state.get('probe_games',0)))) + ' game(s), ' +
               str(max(0,min(40,state.get('probe_mods',0)))) + ' mod(s), ' +
               str(max(0,min(40,state.get('probe_file_lists',0)))) + ' verified release list(s).\n'
               if state.get('scope')=='Provider-only (different game)' and
                  all(type(state.get(k)) is int for k in
                      ('probe_games','probe_mods','probe_file_lists')) else '')
            + 'Real-game installation: Not attempted\n'
            'Private key, account IDs, mod IDs, paths and download URLs: excluded.\n')
