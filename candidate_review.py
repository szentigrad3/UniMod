"""Review-only ordering of provider catalogue results for installed mods.

Search similarity is NOT provenance, compatibility, publisher verification or
permission to download. Never return an approved source or persist results.
"""
import re
import unicodedata
from urllib.parse import urlsplit

STOP = frozenset({'bep', 'ex', 'in', 'mod', 'mods', 'plugin', 'plugins', 'bepinex', 'graveyard', 'keeper',
                  'game', 'the', 'a', 'an', 'for', 'of', 'and', 'edition', 'updated',
                  'remastered', 'dll', 'zip', 'patch', 'fix', 'new', 'official'})


def terms(text):
    if not isinstance(text,str) or len(text)>300:
        return frozenset()
    text=unicodedata.normalize('NFKC',text)
    text=re.sub(r'(?<=[a-z0-9])(?=[A-Z])',' ',text)
    text=re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])',' ',text)
    tokens=re.findall(r'[a-z0-9]+',text.casefold())
    return frozenset(t for t in tokens if len(t)>=2 and t not in STOP and not t.isnumeric())


def _nexus_game_ok(url, domain):
    try:
        u=urlsplit(url)
        return (u.scheme=='https' and u.hostname=='www.nexusmods.com' and
                u.username is None and u.password is None and u.port in (None,443) and
                u.path.startswith('/'+domain+'/mods/') and
                bool(re.fullmatch(r'/[a-z][a-z0-9-]{1,79}/mods/[1-9][0-9]{0,11}/?',u.path)) and
                not u.query and not u.fragment)
    except (ValueError,TypeError):
        return False


def review_hint(search_query, candidate, game_domain=None):
    """Return a search-relevance label for a human; never an identity assertion."""
    if not isinstance(candidate,dict):return {'band':0,'hint':'Invalid result'}
    if candidate.get('provider')=='Nexus Mods' and game_domain:
        if not _nexus_game_ok(candidate.get('url'),game_domain):
            return {'band':0,'hint':'Different Nexus game — do not link'}
    wanted=terms(search_query)
    title=terms(candidate.get('title'))
    if not wanted or not title:
        return {'band':1,'hint':'Insufficient title evidence — inspect manually'}
    common=len(wanted & title)
    if wanted==title:
        return {'band':4,'hint':'Same title terms — still unverified'}
    if common and wanted.issubset(title):
        return {'band':3,'hint':'Search terms included — still unverified'}
    if common:
        return {'band':2,'hint':'Partial title overlap — inspect manually'}
    return {'band':1,'hint':'No title overlap — inspect manually'}


def order_for_review(search_query, records, *, game_domain=None):
    """Stable, descending relevance. Copy records without changing approved links."""
    decorated=[]
    for index, row in enumerate(records):
        hint=review_hint(search_query,row,game_domain)
        new=dict(row)
        new['review_hint']=hint['hint']
        new['review_band']=hint['band']
        decorated.append((hint['band'],index,new))
    decorated.sort(key=lambda row:(-row[0],row[1]))
    return [r[2] for r in decorated]
