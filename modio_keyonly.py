"""Resolve a selected installed game's public mod.io ID without asking for IDs.

This uses the documented legacy/global public GET catalogue endpoint. Some
account-scoped keys only work on their issued unique API path; in that case
return an explicit unsupported/connection outcome, never guess an account ID.
"""
import re
from urllib.parse import urlencode
import provider_catalogues as catalogue


class ResolutionError(ValueError):
    pass


def api_base(user_id=None):
    """Use a verified user API path when supplied, else the legacy read-only API."""
    return (f'https://u-{catalogue.numeric(user_id)}.modapi.io/v1'
            if user_id is not None else 'https://api.mod.io/v1')


def _normal(name):
    return re.sub('[^a-z0-9]', '', str(name or '').casefold())


def resolve_game(game, api_key, *, fetch=None, user_id=None):
    """Require one unambiguous exact-name game match from a complete page."""
    if not isinstance(game, dict) or game.get('kind') not in ('smapi','bepinex'):
        raise ResolutionError('choose_game')
    name=game.get('name')
    if not isinstance(name,str) or not 2 <= len(name.strip()) <= 120:
        raise ResolutionError('choose_game')
    if not isinstance(api_key,str) or len(api_key.strip())<8:
        raise ResolutionError('connect')
    # Do not use /me: it requires OAuth, not an API key.
    query=urlencode({'api_key':api_key.strip(),'_q':name.strip(),'_limit':100})
    try:
        page=catalogue.fetch_json(api_base(user_id)+'/games?'+query,fetch=fetch)
    except Exception:
        raise ResolutionError('key_path_required') from None
    if not isinstance(page,dict) or not isinstance(page.get('data'),list):
        raise ResolutionError('game_api')
    rows=page['data']
    try:
        total=int(page.get('result_total',len(rows)))
    except (ValueError,TypeError,OverflowError):
        raise ResolutionError('ambiguous_game') from None
    # A truncated response cannot prove uniqueness. Decline to guess.
    if total>len(rows):
        raise ResolutionError('ambiguous_game')
    found=set()
    for item in rows:
        if not isinstance(item,dict) or _normal(item.get('name'))!=_normal(name):
            continue
        ident=str(item.get('id') or '')
        if re.fullmatch(r'[1-9][0-9]{0,11}',ident):
            found.add(ident)
    if len(found)!=1:
        raise ResolutionError('ambiguous_game' if len(found)>1 else 'game_not_found')
    return next(iter(found))


def public_test_game_ids(api_key, *, fetch=None, user_id=None):
    """Bounded sample of heavily modded official games for provider-only tests.

    The selected installed game is NOT inferred from these records.
    Returns IDs only. No secret data, names or URLs are persisted.
    """
    if not isinstance(api_key,str) or len(api_key.strip())<8:
        raise ResolutionError('connect')
    # Recently published games often have zero mods. The documented
    # mods_count_total sort favours established public catalogues and makes
    # the approved provider-only test much more likely to find an eligible ZIP.
    url = api_base(user_id) + '/games?' + urlencode({
        'api_key':api_key.strip(), '_limit':30, '_sort':'-mods_count_total'})
    try:
        response = catalogue.fetch_json(url,fetch=fetch)
    except Exception:
        raise ResolutionError('key_path_required') from None
    if not isinstance(response,dict) or not isinstance(response.get('data'),list):
        raise ResolutionError('game_api')
    result=[]
    for item in response['data'][:30]:
        ident=str(item.get('id') or '') if isinstance(item,dict) else ''
        if re.fullmatch(r'[1-9][0-9]{0,11}',ident) and ident not in result:
            result.append(ident)
        if len(result)>=8:
            break
    return result
