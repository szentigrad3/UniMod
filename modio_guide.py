"""Private and redacted readiness checks for the beginner mod.io test guide."""
import hashlib
import re
from pathlib import Path


def _numeric(value):
    return isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,11}', value.strip()) is not None


def _normalized(value):
    return re.sub('[^a-z0-9]', '', str(value or '').casefold())


def snapshot(game, provider, game_id, user_id, api_key, verified, selected=None, test_results=None):
    """Determine next steps without showing credentials or local paths."""
    game_ok = (isinstance(game, dict) and game.get('kind') in ('smapi','bepinex')
               and isinstance(game.get('root'), str) and bool(game.get('root')))
    gid = game_id.strip() if isinstance(game_id, str) else ''
    uid = user_id.strip() if isinstance(user_id, str) else ''
    key = api_key.strip() if isinstance(api_key, str) else ''
    fields = provider == 'mod.io' and _numeric(gid) and _numeric(uid) and len(key) >= 8
    digest = hashlib.sha256(key.encode()).digest() if fields else None
    verified_ok = (game_ok and fields and isinstance(verified, tuple)
                   and len(verified) >= 4 and verified[:3] == (gid, uid, digest)
                   and bool(_normalized(verified[3]))
                   and _normalized(game.get('name')) == _normalized(verified[3]))
    identity = ''
    if isinstance(selected, dict) and selected.get('provider') == 'mod.io':
        name = selected.get('identity')
        if isinstance(name, str) and re.fullmatch(r'[1-9][0-9]{0,11}/[1-9][0-9]{0,11}', name):
            if name.split('/')[0] == gid:
                identity = name
    selected_ok = bool(verified_ok and identity)
    root = str(Path(game['root']).resolve()) if game_ok else ''
    context = (root, identity, uid, digest) if selected_ok else None
    record = test_results if isinstance(test_results, dict) else {}

    def test(name):
        value = record.get(name)
        if (context is not None and isinstance(value, dict)
                and value.get('context') == context
                and value.get('result') in ('Passed', 'Failed')):
            return value['result']
        return 'Not tested'

    return {'game_selected': bool(game_ok), 'connection_entered': bool(fields),
            'game_verified': bool(verified_ok), 'mod_selected': selected_ok,
            'metadata_test': test('metadata'), 'download_test': test('download'),
            '_context': context}


def safe_report(state):
    """Copyable report; never include game/account IDs, key, signed URL or local path."""
    def yes(name):
        return 'Yes' if state.get(name) is True else 'No'
    def result(name):
        value = state.get(name)
        return value if value in ('Passed', 'Failed', 'Not tested') else 'Not tested'
    return ('UniMod mod.io tester report (v0.56 development)\n'
            'Supported game selected: ' + yes('game_selected') + '\n'
            'mod.io details entered: ' + yes('connection_entered') + '\n'
            'Game verified: ' + yes('game_verified') + '\n'
            'mod.io mod selected: ' + yes('mod_selected') + '\n'
            'Metadata check: ' + result('metadata_test') + '\n'
            'Temporary download check: ' + result('download_test') + '\n'
            'Real installation/rollback: Not tested in this guide\n'
            'Privacy: API keys, user/game/mod IDs, signed URLs, and local paths omitted.\n')


def next_step(state):
    if not state.get('game_selected'):
        return '1. Choose an installed SMAPI or BepInEx game.'
    if not state.get('connection_entered'):
        return '2. Enter your mod.io game ID, account API-path ID and private key in Discover.'
    if not state.get('game_verified'):
        return '2. Click Verify mod.io game ID and confirm the matching title.'
    if not state.get('mod_selected'):
        return '3. Search mod.io and select one result from your verified game.'
    if state.get('metadata_test') != 'Passed':
        return '4. Click Test mod.io API to check read-only metadata.'
    if state.get('download_test') != 'Passed':
        return '5. Open release files and use Test download (temporary) on a small ZIP.'
    return 'Checks passed. Review a separate inbox download and compatibility before any installation.'
