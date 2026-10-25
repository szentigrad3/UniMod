"""Read-only, provider-specific catalogue discovery for UniMod.

Search results are leads to official pages, NOT authenticated provenance for an
installed mod. No name search result is automatically bound to an installed mod.
No account secret is logged, stored or returned in a result. Only explicit,
provider-issued API requests are allowed; no search-engine scraping.
"""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

VERSION = '0.55.0-test12'
MAX_RESPONSE = 5 * 1024 * 1024
SEARCH_LIMIT = 40
THUNDERSTORE_LIMIT = 30 * 1024 * 1024
PROVIDERS = ('Nexus Mods', 'Thunderstore', 'GitHub', 'Modrinth', 'CurseForge', 'mod.io')
KEYED_PROVIDERS = ('CurseForge', 'mod.io')

class ProviderError(ValueError):
    """No server error body, URL query or credentials are revealed."""


def clean_search(text):
    if not isinstance(text, str) or not 2 <= len(text.strip()) <= 120 or any(ord(c)<32 for c in text):
        raise ProviderError('Enter a search term between 2 and 120 characters.')
    return text.strip()


def slug(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', value):
        raise ProviderError('Choose a valid community or game identifier.')
    return value


def numeric(value):
    if not re.fullmatch(r'[1-9]\d{0,11}', str(value)):
        raise ProviderError('Choose a valid positive game identifier.')
    return str(value)


class NoOffsiteRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hostname):
        self.hostname = hostname
    def redirect_request(self, req, fp, code, msg, hdrs, newurl):
        u = urllib.parse.urlsplit(newurl)
        if u.scheme != 'https' or u.hostname != self.hostname or u.username or u.password or u.port not in (None, 443):
            raise ProviderError('The provider redirected outside its API host.')
        return super().redirect_request(req, fp, code, msg, hdrs, newurl)


def fetch_json(url, *, headers=None, fetch=None, limit=MAX_RESPONSE):
    """Safe JSON read; injected fetch(url, headers) makes offline testing possible."""
    parsed=urllib.parse.urlsplit(url)
    allowed={'api.github.com', 'api.modrinth.com', 'thunderstore.io', 'api.curseforge.com', 'api.mod.io'}
    if parsed.hostname not in allowed and not re.fullmatch(r'[gu]-[1-9]\d{0,11}\.modapi\.io', parsed.hostname or ''):
        raise ProviderError('Unapproved provider API host.')
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment:
        raise ProviderError('Provider APIs require HTTPS.')
    headers={'Accept':'application/json', 'User-Agent':'UniMod/0.55-test12 (Linux mod manager)', **(headers or {})}
    if fetch is not None:
        result=fetch(url, dict(headers))
    else:
        try:
            req=urllib.request.Request(url, headers=headers)
            opener=urllib.request.build_opener(NoOffsiteRedirect(parsed.hostname))
            with opener.open(req, timeout=15) as response:
                raw=response.read(limit+1)
            if len(raw)>limit: raise ProviderError('Catalogue response too large.')
            result=json.loads(raw)
        except urllib.error.HTTPError as ex:
            if ex.code in (401,403): raise ProviderError('Provider authentication or API access is required.') from None
            if ex.code==429: raise ProviderError('Provider rate limit reached. Try later.') from None
            raise ProviderError(f'Provider request failed (HTTP {ex.code}).') from None
        except urllib.error.URLError:
            raise ProviderError('Could not connect to the provider. Check your network.') from None
        except (TimeoutError, OSError):
            raise ProviderError('Provider request timed out.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ProviderError('Provider returned invalid JSON.') from None
    if not isinstance(result, (dict,list)):
        raise ProviderError('Unexpected provider response.')
    return result


def _result(provider, title, author, version, url, detail='', identity='', downloads=0):
    return {'provider':provider,'title':str(title)[:180],'author':str(author)[:120],
            'version':str(version)[:70], 'url':url,'description':str(detail)[:420],
            'identity':str(identity)[:180],'downloads':int(downloads or 0)}


def search_github(query, *, fetch=None):
    q=clean_search(query)
    url='https://api.github.com/search/repositories?'+urllib.parse.urlencode({'q':q+' in:name,description','per_page':SEARCH_LIMIT})
    data=fetch_json(url,fetch=fetch)
    results=[]
    for entry in (data.get('items') or [])[:SEARCH_LIMIT]:
        if not isinstance(entry,dict):continue
        fullname=entry.get('full_name') or ''
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}',fullname):continue
        if entry.get('archived'):continue
        author,repo=fullname.split('/',1)
        results.append(_result('GitHub',entry.get('name') or repo,author,'',
                     'https://github.com/'+fullname,entry.get('description') or '',fullname))
    return results


def search_modrinth(query, *, fetch=None):
    q=clean_search(query)
    url='https://api.modrinth.com/v2/search?'+urllib.parse.urlencode({'query':q,'limit':SEARCH_LIMIT})
    data=fetch_json(url,fetch=fetch)
    results=[]
    for entry in (data.get('hits') or [])[:SEARCH_LIMIT]:
        if not isinstance(entry,dict):continue
        pid=str(entry.get('project_id') or '')
        if not re.fullmatch(r'[a-zA-Z0-9]{3,50}',pid):continue
        typ=entry.get('project_type') or 'mod'
        if typ not in ('mod','modpack','resourcepack','shader'):continue
        results.append(_result('Modrinth',entry.get('title') or pid,entry.get('author') or '',
                      '',f'https://modrinth.com/{typ}/{pid}',entry.get('description') or '',pid,
                      entry.get('downloads') or 0))
    return results


def search_thunderstore(query, community, *, fetch=None):
    q=clean_search(query).casefold(); com=slug(community).lower()
    url=f'https://thunderstore.io/c/{com}/api/v1/package/'
    data=fetch_json(url,fetch=fetch,limit=THUNDERSTORE_LIMIT)
    if not isinstance(data,list):raise ProviderError('Unexpected Thunderstore catalogue.')
    results=[]
    for entry in data:
        if not isinstance(entry,dict):continue
        owner=entry.get('owner') or ''; name=entry.get('name') or ''
        if not all(isinstance(v,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',v) for v in (owner,name)):continue
        versions=entry.get('versions') or []
        latest=versions[0] if isinstance(versions,list) and versions and isinstance(versions[0],dict) else {}
        description=str(latest.get('description') or '')
        if q not in (' '.join([owner,name,description])).casefold(): continue
        results.append(_result('Thunderstore',name,owner,latest.get('version_number') or '',
                      f'https://thunderstore.io/c/{com}/p/{owner}/{name}/',description,
                      f'{com}/{owner}/{name}',entry.get('total_downloads') or 0))
        if len(results)>=SEARCH_LIMIT:break
    return results


def _curseforge_key(api_key):
    if not isinstance(api_key,str) or len(api_key.strip()) < 8:
        raise ProviderError('CurseForge API access requires an approved API key.')
    return api_key.strip()


def curseforge_game(game_id, api_key, *, fetch=None):
    """Validate the actual game name against the official API (read-only)."""
    gid=numeric(game_id);key=_curseforge_key(api_key)
    data=fetch_json(f'https://api.curseforge.com/v1/games/{gid}',
                    headers={'x-api-key':key},fetch=fetch)
    raw=data.get('data') if isinstance(data,dict) else None
    if not isinstance(raw,dict) or str(raw.get('id'))!=gid:
        raise ProviderError('CurseForge did not confirm the selected game ID.')
    name=raw.get('name');slug_name=raw.get('slug')
    if not isinstance(name,str) or not name.strip() or len(name)>150:
        raise ProviderError('CurseForge returned an invalid game name.')
    if not isinstance(slug_name,str) or not re.fullmatch(r'[a-zA-Z0-9-]{1,120}',slug_name):
        slug_name=''
    return {'id':gid,'name':name.strip(),'slug':slug_name}


def curseforge_files(identity, api_key, *, fetch=None):
    """Read-only file release metadata, never return provider download URLs."""
    if not isinstance(identity,str) or not re.fullmatch(r'[1-9]\d{0,11}/[1-9]\d{0,11}',identity):
        raise ProviderError('Select an exact CurseForge project result.')
    game_id,mod_id=identity.split('/')
    key=_curseforge_key(api_key)
    params=urllib.parse.urlencode({'index':0,'pageSize':50})
    data=fetch_json(f'https://api.curseforge.com/v1/mods/{mod_id}/files?{params}',
                    headers={'x-api-key':key},fetch=fetch)
    entries=data.get('data') if isinstance(data,dict) else None
    if not isinstance(entries,list):raise ProviderError('Invalid CurseForge file listing.')
    out=[]
    for entry in entries[:50]:
        if not isinstance(entry,dict) or str(entry.get('modId'))!=mod_id or str(entry.get('gameId'))!=game_id:
            continue
        if not re.fullmatch(r'[1-9]\d{0,11}',str(entry.get('id'))):continue
        if entry.get('isAvailable') is False:continue
        filename=entry.get('fileName')
        if not isinstance(filename,str) or not 1<=len(filename)<=220 or filename in ('.','..') or any(ord(c)<32 for c in filename) or '/' in filename or '\\' in filename:continue
        try: size=int(entry.get('fileLength',0))
        except (ValueError,TypeError):continue
        if not 0<=size<=2**40:continue
        versions=entry.get('gameVersions')
        if not isinstance(versions,list):versions=[]
        versions=[x[:80] for x in versions[:15] if isinstance(x,str) and len(x)<=80]
        out.append({'file_id':str(entry['id']),'filename':filename,'size':size,
                    'display':str(entry.get('displayName') or '')[:160],
                    'date':str(entry.get('fileDate') or '')[:30],
                    'versions':versions,'release_type':{1:'Release',2:'Beta',3:'Alpha'}.get(entry.get('releaseType'),'Other')})
    return out


def search_curseforge(query, game_id, api_key, *, fetch=None):
    q=clean_search(query); gid=numeric(game_id)
    if not api_key or not isinstance(api_key,str) or len(api_key.strip())<8:
        raise ProviderError('CurseForge API access requires an approved API key.')
    url='https://api.curseforge.com/v1/mods/search?'+urllib.parse.urlencode({'gameId':gid,'searchFilter':q,'pageSize':SEARCH_LIMIT})
    data=fetch_json(url,headers={'x-api-key':api_key.strip()},fetch=fetch)
    results=[]
    for entry in (data.get('data') or [])[:SEARCH_LIMIT]:
        if not isinstance(entry,dict):continue
        link=((entry.get('links') or {}).get('websiteUrl') or '')
        try: parsed=urllib.parse.urlsplit(link)
        except (ValueError,TypeError):continue
        if parsed.scheme!='https' or parsed.hostname not in ('www.curseforge.com','curseforge.com') or parsed.username or parsed.password or parsed.port not in (None,443):continue
        mid=entry.get('id')
        if not re.fullmatch(r'[1-9]\d{0,11}',str(mid)):continue
        if entry.get('gameId') is not None and str(entry['gameId'])!=gid:continue
        authors=entry.get('authors') or []
        author=authors[0].get('name','') if isinstance(authors,list) and authors and isinstance(authors[0],dict) else ''
        results.append(_result('CurseForge',entry.get('name') or 'Unknown',author,'',
                           parsed._replace(query='',fragment='').geturl(),entry.get('summary') or '',f'{gid}/{mid}',entry.get('downloadCount') or 0))
    return results


def modio_game(game_id, api_key, *, user_id, fetch=None):
    """Resolve the game title through the user's own documented mod.io API path.

    Credentials are only used in a bounded HTTPS GET and never returned in the
    resulting public game record. This does not enable downloads or user writes.
    """
    gid=numeric(game_id);uid=numeric(user_id)
    if not isinstance(api_key,str) or len(api_key.strip()) < 8:
        raise ProviderError('Enter a mod.io user API key for this session.')
    base=f'https://u-{uid}.modapi.io/v1'
    address=base+f'/games/{gid}?'+urllib.parse.urlencode({'api_key':api_key.strip()})
    record=fetch_json(address,fetch=fetch)
    if not isinstance(record,dict) or str(record.get('id')) != gid:
        raise ProviderError('mod.io did not confirm the requested game ID.')
    name=record.get('name')
    if not isinstance(name,str) or not name.strip() or len(name)>180:
        raise ProviderError('mod.io returned an invalid game name.')
    return {'id':gid,'name':name.strip()}


def search_modio(query, game_id, api_key, *, user_id=None, fetch=None):
    q=clean_search(query);gid=numeric(game_id)
    if not api_key or not isinstance(api_key,str) or len(api_key.strip())<8:
        raise ProviderError('mod.io requires a user API key for read-only catalogue access.')
    # mod.io issues a user-specific API path to user-created tooling. The
    # legacy game path stays available for test fixtures and game-admin keys.
    prefix=(f'u-{numeric(user_id)}' if user_id is not None else f'g-{gid}')
    address=f'https://{prefix}.modapi.io/v1/games/{gid}/mods?'+urllib.parse.urlencode({'_q':q,'_limit':SEARCH_LIMIT,'api_key':api_key.strip()})
    data=fetch_json(address,fetch=fetch)
    if not isinstance(data,dict) or not isinstance(data.get('data'),list):
        raise ProviderError('mod.io returned an invalid mod catalogue.')
    results=[]
    for entry in data['data'][:SEARCH_LIMIT]:
        if not isinstance(entry,dict):continue
        mid=entry.get('id');name=entry.get('name');name_id=entry.get('name_id')
        if not re.fullmatch(r'[1-9]\d{0,11}',str(mid)):continue
        if entry.get('game_id') is not None and str(entry['game_id'])!=gid:continue
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',str(name_id or '')):continue
        # The official profile URL must be present. Never guess a game slug.
        profile=entry.get('profile_url') or ''
        try: pu=urllib.parse.urlsplit(profile)
        except (ValueError,TypeError):continue
        if (pu.scheme!='https' or pu.hostname not in ('mod.io','www.mod.io')
            or pu.username or pu.password or pu.port not in (None,443)
            or pu.query or pu.fragment):continue
        results.append(_result('mod.io',name or name_id,'', '',pu.geturl(),
                               entry.get('summary') or '',f'{gid}/{mid}'))
    return results


# Read-only public GraphQL V2 metadata search. OAuth/client registration is NOT used.
# Explicitly scoped to the selected game's verified Nexus domain.
NEXUS_GRAPHQL_ENDPOINT = 'https://api.nexusmods.com/v2/graphql'
NEXUS_SEARCH_QUERY = '''query UniModCatalogue($filter: ModsFilter, $count: Int) {
  mods(filter: $filter, count: $count, offset: 0) {
    nodes { modId name summary version downloads uploader { name } game { domainName } }
  }
}'''


def nexus_game_domain(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,79}',value):
        raise ProviderError('Select a game with a verified Nexus Mods game domain.')
    return value


def nexus_public_graphql(payload, *, fetch=None):
    """Send a bounded POST only to Nexus' documented public metadata API."""
    body=json.dumps(payload,separators=(',',':')).encode('utf-8')
    if len(body)>16*1024: raise ProviderError('Search request too large.')
    headers={'Accept':'application/json','Content-Type':'application/json',
             'User-Agent':'UniMod/0.55-test12 (Linux mod manager)',
             'Application-Name':'UniMod','Application-Version':'0.55-test10'}
    if fetch is not None:
        result=fetch(NEXUS_GRAPHQL_ENDPOINT,dict(headers),body)
    else:
        try:
            req=urllib.request.Request(NEXUS_GRAPHQL_ENDPOINT,data=body,headers=headers,method='POST')
            opener=urllib.request.build_opener(NoOffsiteRedirect('api.nexusmods.com'))
            with opener.open(req,timeout=15) as response:
                raw=response.read(2*1024*1024+1)
            if len(raw)>2*1024*1024: raise ProviderError('Nexus response too large.')
            result=json.loads(raw)
        except urllib.error.HTTPError as ex:
            if ex.code in (401,403): raise ProviderError('Nexus catalogue access denied. Use the official website.') from None
            if ex.code==429: raise ProviderError('Nexus rate limit reached. Try later.') from None
            raise ProviderError(f'Nexus metadata search failed (HTTP {ex.code}).') from None
        except urllib.error.URLError:
            raise ProviderError('Could not reach Nexus Mods. Use the official website.') from None
        except (TimeoutError,OSError):
            raise ProviderError('Nexus Mods connection timed out.') from None
        except (json.JSONDecodeError,UnicodeDecodeError):
            raise ProviderError('Nexus Mods returned invalid JSON.') from None
    if not isinstance(result,dict):raise ProviderError('Unexpected Nexus Mods response.')
    if result.get('errors'):raise ProviderError('Nexus Mods rejected the metadata query; use its official website.')
    return result


def search_nexus(query, game_domain, *, fetch=None):
    q=clean_search(query)
    domain=nexus_game_domain(game_domain)
    # The game-domain equality is mandatory, preventing results for other games.
    # Stemmed matching supports site-side token matching without scraping.
    payload={'query':NEXUS_SEARCH_QUERY,'variables':{'count':SEARCH_LIMIT,
             'filter':{'gameDomainName':[{'value':domain,'op':'EQUALS'}],
                       'nameStemmed':[{'value':q,'op':'MATCHES'}]}}}
    response=nexus_public_graphql(payload,fetch=fetch)
    mods=(response.get('data') or {}).get('mods') or {}
    if not isinstance(mods,dict) or not isinstance(mods.get('nodes'),list):
        raise ProviderError('Nexus catalogue response is missing mod results.')
    results=[]
    for entry in mods['nodes'][:SEARCH_LIMIT]:
        if not isinstance(entry,dict):continue
        game=entry.get('game') or {}
        if not isinstance(game,dict) or game.get('domainName') != domain:continue
        mid=entry.get('modId')
        if not re.fullmatch(r'[1-9][0-9]{0,11}',str(mid)):continue
        author=entry.get('uploader') or {}
        if not isinstance(author,dict):author={}
        results.append(_result('Nexus Mods',entry.get('name') or str(mid),
             author.get('name') or '',entry.get('version') or '',
             f'https://www.nexusmods.com/{domain}/mods/{mid}',
             entry.get('summary') or '',f'{domain}/{mid}',entry.get('downloads') or 0))
    return results


def search(provider, query, *, community='', game_id='', key='', user_id=None, fetch=None):
    if provider=='Nexus Mods':return search_nexus(query,community,fetch=fetch)
    if provider=='GitHub':return search_github(query,fetch=fetch)
    if provider=='Modrinth':return search_modrinth(query,fetch=fetch)
    if provider=='Thunderstore':return search_thunderstore(query,community,fetch=fetch)
    if provider=='CurseForge':return search_curseforge(query,game_id,key,fetch=fetch)
    if provider=='mod.io':return search_modio(query,game_id,key,user_id=user_id,fetch=fetch)
    raise ProviderError('Unsupported catalogue provider.')


def readiness(app_slug=None, websocket_available=None):
    """Local readiness only. Never asserts Nexus has approved the application."""
    if websocket_available is None:
        try: import websocket; websocket_available=bool(websocket.create_connection)
        except ImportError: websocket_available=False
    return {'nexus_registration':'awaiting Nexus OAuth registration; legacy SSO slug optional',
            'sso_runtime_installed':bool(websocket_available),
            'slug_configured':bool(app_slug),
            'required_from_nexus':['OAuth public client ID and registered redirect URI','Approved OAuth authorize/token endpoints and scopes','Confirmed REST download API version and restrictions','Approved application slug (legacy SSO fallback only)','Any reviewer-requested changes'],
            'already_implemented':['Session-only key','SSO browser + WebSocket client','Official NXM handler','Exact mod/file API','Review queue and ZIP validation','Backup-protected installs']}
