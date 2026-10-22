"""Conservative SMAPI exact-UniqueID source resolution.

The SMAPI web API is publicly documented for external tools but not a stable
versioned contract. No key is needed. Never search by an arbitrary mod name,
never scrape Nexus, and never send local paths, filenames, or user credentials.
"""
import json
import re
import urllib.request
from urllib.parse import urlsplit, parse_qs

URL = 'https://smapi.io/api/v4.5.2/mods'
# SMAPI itself ships these components; its own update checks suppress them.
BUNDLED_SMAPI_IDS = frozenset({'smapi.consolecommands', 'smapi.savebackup'})
VALID_UID = re.compile(r'^[A-Za-z0-9_.-]{1,180}$')
VALID_NEXUS = re.compile(r'^[1-9][0-9]{0,11}$')


def resolve_smapi_ids(mods, fetch=None, diagnostics=False):
    """Return exact matches indexed by case-folded manifest UniqueID.

    Only name-independent metadata matches are accepted. `fetch` accepts
    (URL, JSON payload) and returns parsed JSON for deterministic offline tests.
    """
    wanted = {}
    bundled = 0
    for mod in mods:
        uid = str(mod.get('uid') or '').strip()
        if uid.casefold() in BUNDLED_SMAPI_IDS:
            bundled += 1
            continue
        if VALID_UID.fullmatch(uid):
            wanted.setdefault(uid.casefold(), {'id': uid,
                'installedVersion': str(mod.get('version') or '')[:60],
                'updateKeys': [x for x in mod.get('update_keys', [])
                              if isinstance(x, str) and len(x) <= 256][:12]})
    if not wanted:
        return {'matches':{},'requested':0,'returned':0,'no_metadata':0,'no_nexus':0,'api_errors':0,'bundled':bundled, 'matched_by_main':0,'error_ids':[]} if diagnostics else {}
    if len(wanted) > 150:
        raise ValueError('Too many mods for one catalogue lookup')
    payload={'mods': list(wanted.values()), 'apiVersion':'4.5.2',
             'platform':'Linux','includeExtendedMetadata':True}
    if fetch is None:
        body=json.dumps(payload,separators=(',',':')).encode('utf-8')
        if len(body)>100_000:
            raise ValueError('SMAPI catalogue request too large')
        req=urllib.request.Request(URL,data=body,method='POST',headers={
            'Content-Type':'application/json','Accept':'application/json',
            'User-Agent':'UniMod/0.51'})
        class SameHostOnly(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,request,fp,code,msg,headers,newurl):
                parsed=urlsplit(newurl)
                if parsed.scheme != 'https' or parsed.hostname != 'smapi.io':
                    raise ValueError('SMAPI response redirected off smapi.io')
                return super().redirect_request(request,fp,code,msg,headers,newurl)
        with urllib.request.build_opener(SameHostOnly()).open(req,timeout=18) as response:
            if int(response.headers.get('Content-Length') or 0)>2_000_000:
                raise ValueError('SMAPI catalogue response too large')
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:raise ValueError('SMAPI catalogue response too large')
            data=json.loads(raw)
    else:data=fetch(URL,payload)
    if not isinstance(data,list):raise ValueError('Unexpected SMAPI catalogue response')
    verified={}
    reasons={'requested':len(wanted),'returned':len(data),'no_metadata':0,'no_nexus':0,'api_errors':0,'bundled':bundled,'matched_by_main':0,'error_ids':[]}
    for record in data:
        if not isinstance(record,dict):continue
        uid=str(record.get('id') or '').strip().casefold()
        if uid not in wanted or uid in verified:continue
        if record.get('errors'):
            reasons['api_errors']+=1
            reasons['error_ids'].append(uid)
            continue
        metadata=record.get('metadata')
        if not isinstance(metadata,dict):
            metadata={}
            reasons['no_metadata']+=1
        aliases=metadata.get('id')
        if isinstance(aliases,list) and aliases and uid not in {
            str(x).casefold() for x in aliases if isinstance(x,str)}:
            reasons['api_errors']+=1
            reasons['error_ids'].append(uid)
            continue
        # SMAPI may omit suggestedUpdate when the installed version is current.
        # Its canonical metadata.main URL can still identify the original Nexus
        # page. Avoid optional/unofficial versions: those may be unrelated patches.
        def exact_stardew_nexus(url):
            try:
                parts=urlsplit(str(url or ''))
                if (parts.scheme != 'https' or parts.hostname not in
                        ('www.nexusmods.com','nexusmods.com') or
                        parts.username or parts.password or parts.port not in (None,443)):
                    return ''
                match=re.fullmatch(r'/stardewvalley/mods/([1-9][0-9]{0,11})/?',parts.path,re.I)
                return match.group(1) if match else ''
            except ValueError:
                return ''
        number=str(metadata.get('nexusID') or '').strip()
        if not VALID_NEXUS.fullmatch(number):number=''
        main=metadata.get('main')
        main_id=exact_stardew_nexus(main.get('url')) if isinstance(main,dict) else ''
        suggestion=record.get('suggestedUpdate')
        suggested_id=exact_stardew_nexus(suggestion.get('url')) if isinstance(suggestion,dict) else ''
        authoritative={v for v in (number,main_id) if v}
        # Even the canonical metadata fields can disagree due to stale content.
        # Fail closed rather than attach the wrong Nexus page automatically.
        if len(authoritative)>1:
            reasons['api_errors']+=1
            reasons['error_ids'].append(uid)
            continue
        if authoritative:
            number=next(iter(authoritative))
            if suggested_id and suggested_id!=number:
                reasons['api_errors']+=1
                reasons['error_ids'].append(uid)
                continue
            if not metadata.get('nexusID') and main_id:
                reasons['matched_by_main']+=1
            # A suggested update can be an unofficial patch on another Nexus
            # page. Do not replace a canonical main ID with that suggestion.
        elif suggested_id:
            number=suggested_id
        else:
            reasons['no_nexus']+=1
            continue
        verified[uid]={'nexus_id':number,
                       'url':f'https://www.nexusmods.com/stardewvalley/mods/{number}',
                       'source':'SMAPI exact UniqueID metadata'}
    if diagnostics:
        return {'matches':verified,**reasons}
    return verified
