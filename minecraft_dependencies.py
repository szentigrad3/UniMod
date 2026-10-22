"""UniMod 0.55 test: explicit-review Modrinth required-dependency workflow.

Planning is read-only. Only a user-confirmed operation downloads exact HTTPS
Modrinth CDN files; downloads precede game writes. JARs install in dependency
order and a failed batch attempts to restore all modified managed files.
"""
import hashlib
import re
import urllib.parse
from pathlib import Path

import minecraft_profiles as profiles
import provider_catalogues as catalogue
import provider_downloads as downloads
import provider_staging as staging

MAX_NODES = 24
MAX_DEPTH = 12
MAX_BATCH_BYTES = 2*1024*1024*1024
ID = re.compile(r'[A-Za-z0-9_-]{3,70}\Z')

class ResolutionError(profiles.MinecraftError):
    pass


def _ident(value):
    if not isinstance(value,str) or not ID.fullmatch(value):
        raise ResolutionError('Required dependency does not have a usable Modrinth ID.')
    return value


def _known_dependency(dep, profile, receipts):
    """Require matching installation receipt and file digest, never a guessed JAR name."""
    project = dep.get('project_id') or (dep.get('id') if not dep.get('version_id') else '') or ''
    version = dep.get('version_id') or ''
    mods = Path(profile['mods'])
    for rec in receipts:
        if rec.get('profile') != profile['root']:continue
        if project and rec.get('project_id') != project:continue
        if version and rec.get('version_id') != version:continue
        target=Path(str(rec.get('installed_path') or ''))
        if target.parent!=mods or target.is_symlink() or not target.is_file():continue
        if staging.file_sha256(target)==rec.get('installed_hash'):return True
    return False


def _dependencies(record):
    deps=record.get('dependencies') or []
    if not isinstance(deps,list) or len(deps)>60:
        raise ResolutionError('Dependency metadata is missing or malformed.')
    required=[]
    for dep in deps:
        if not isinstance(dep,dict):raise ResolutionError('Unrecognised Modrinth dependency record.')
        kind=str(dep.get('type') or dep.get('dependency_type') or '').lower()
        if kind in ('incompatible','unknown',''):
            raise ResolutionError('An incompatible or unknown dependency requires manual review.')
        if kind=='required':required.append(dep)
        elif kind not in ('optional','embedded'):
            raise ResolutionError('Unknown dependency type; manual review required.')
    return required


def _from_version(payload, pid, version_id, game_version, loader):
    """Select a normal downloadable JAR from a pinned Modrinth version."""
    if not isinstance(payload,dict):raise ResolutionError('Modrinth returned invalid version metadata.')
    own_id=_ident(payload.get('project_id'))
    if pid and own_id!=pid:raise ResolutionError('Pinned dependency belongs to a different Modrinth project.')
    if payload.get('id')!=version_id:raise ResolutionError('Modrinth version ID did not match the request.')
    versions=payload.get('game_versions');loaders=payload.get('loaders')
    if not isinstance(versions,list) or game_version not in versions or not isinstance(loaders,list) or loader not in loaders:
        raise ResolutionError('Pinned dependency does not support this Minecraft version/loader.')
    files=payload.get('files') or []
    choices=[]
    for file in files[:25]:
        if not isinstance(file,dict) or not str(file.get('filename') or '').lower().endswith('.jar'):continue
        if file.get('file_type') in ('sources-jar','dev-jar','javadoc-jar','signature'):continue
        row=downloads._row('Modrinth',own_id,payload.get('version_number') or '',
                           file.get('filename'),file.get('url'),file.get('size'),file.get('hashes'),
                           versions,loaders,payload.get('dependencies'),version_id=version_id)
        if row and row.get('hashes',{}).get('sha512'):
            choices.append((not bool(file.get('primary')),row))
    if not choices:raise ResolutionError('Required dependency has no verified Modrinth JAR download.')
    choices.sort(key=lambda x:x[0])
    if len(choices)>1 and choices[0][0]==choices[1][0]:
        raise ResolutionError('Dependency version has multiple equally ranked JARs; choose manually.')
    return choices[0][1]


def _fetch_version(version_id, *, fetch=None):
    url='https://api.modrinth.com/v2/version/'+urllib.parse.quote(_ident(version_id),safe='')
    return catalogue.fetch_json(url,fetch=fetch)


def _select_project(project_id, version_id, game_version, loader, *, fetch=None):
    if version_id:
        return _from_version(_fetch_version(version_id,fetch=fetch),project_id,version_id,game_version,loader)
    candidates=downloads.modrinth_files(project_id,game_version=game_version,loader=loader,fetch=fetch)
    candidates=[r for r in candidates if r['filename'].lower().endswith('.jar') and
                r['hashes'].get('sha512') and r['version_id'] and
                r.get('file_type') not in ('sources-jar','dev-jar','javadoc-jar','signature')]
    if not candidates:raise ResolutionError('No verifiable compatible Modrinth JAR for '+project_id+'.')
    # Version list is newest first. Respect its primary flag when a version
    # publishes a release JAR plus extra attached artifacts.
    release=[r for r in candidates if r['version_id']==candidates[0]['version_id']]
    primary=[r for r in release if r.get('primary')]
    if len(primary)==1:return primary[0]
    if len(release)==1:return release[0]
    raise ResolutionError('Modrinth dependency version includes ambiguous JARs; choose manually.')


def plan_dependencies(receipt, instance, receipts_path, *, fetch=None):
    """Inspect the parent JAR, then resolve all missing required dependencies.

    No remote file downloads or game writes occur during planning.
    """
    profile=profiles.inspect_instance(instance)
    # A normal preflight validates archive, hashes, game binding and target
    # collisions. It blocks missing dependencies, so validate only those in
    # the separate recursive resolver below.
    base=dict(receipt)
    base['dependencies']=[]
    profiles.preflight(base,instance,receipts_path)
    current=profiles.installed_receipts(receipts_path)
    nodes={};visiting=set();completed=set();order=[]
    planned_ids={};visiting_projects=set()

    def visit(raw, depth):
        if depth>MAX_DEPTH:raise ResolutionError('Dependency chain exceeds safe depth limit.')
        for dep in _dependencies(raw):
            pid=str(dep.get('project_id') or (dep.get('id') if not dep.get('version_id') else '') or '')
            vid=str(dep.get('version_id') or '')
            if pid:pid=_ident(pid)
            if vid:vid=_ident(vid)
            if not pid and not vid:raise ResolutionError('Required dependency has neither project nor version ID.')
            if _known_dependency({'project_id':pid,'version_id':vid},profile,current):continue
            key=pid or 'version:'+vid
            if key in visiting:raise ResolutionError('Circular Modrinth required dependencies detected.')
            if key in completed:
                existing=nodes[key]
                if vid and existing['version_id']!=vid:
                    raise ResolutionError('Conflicting required versions of one Modrinth dependency.')
                continue
            if len(nodes)>=MAX_NODES:raise ResolutionError('Too many automatic required dependencies; install manually.')
            visiting.add(key)
            entry=_select_project(pid,vid,profile['version'],profile['loader'],fetch=fetch)
            eid=_ident(entry['identity'])
            if eid==receipt.get('identity') or eid in visiting_projects:
                raise ResolutionError('Circular Modrinth required dependencies detected.')
            if eid in planned_ids:
                if planned_ids[eid]!=entry['version_id']:
                    raise ResolutionError('Conflicting required versions of one Modrinth project.')
                # The same project can be addressed by project_id or by a
                # version-only reference. It is still one installation.
                nodes[key]=entry
                visiting.remove(key)
                completed.add(key)
                continue
            planned_ids[eid]=entry['version_id']
            nodes[key]=entry
            visiting_projects.add(eid)
            visit(entry,depth+1)
            visiting_projects.remove(eid)
            visiting.remove(key)
            completed.add(key)
            order.append(entry)

    visit(receipt,0)
    # Installed versions and planned versions cannot be mixed to satisfy one
    # pin if the version is wrong; the final installer repeats preflight.
    size=sum(entry['size'] for entry in order)
    if size>MAX_BATCH_BYTES:
        raise ResolutionError('Required dependency downloads exceed the safe 2 GiB batch limit.')
    return {'profile':profile,'parent':receipt,'dependencies':order,
            'downloads':len(order),'bytes':size}


def _file_sha512(path):
    h=hashlib.sha512()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def _recover(installed, journal, old_rows, old_existed):
    issues=[]
    for row in reversed(installed):
        path=Path(row['path']);backup=Path(row['backup']) if row['backup'] else None
        expected=row['hash']
        try:
            if path.is_symlink() or not path.is_file() or staging.file_sha256(path)!=expected:
                raise ResolutionError('Cannot safely roll back changed destination '+path.name)
            path.unlink()
            if backup and backup.is_file():
                old=Path(row['old_path']);backup.replace(old)
        except (OSError,ResolutionError) as exc:
            issues.append(str(exc))
    if not issues:
        try:
            if old_existed:profiles._write_receipts(journal,old_rows)
            else:Path(journal).unlink(missing_ok=True)
        except OSError as exc:issues.append('Could not restore install receipts: '+str(exc))
    return issues


def install_plan(plan, inbox, staging_journal, receipts_path, recovery_dir, *, downloader=None):
    """Download *all* dependencies before modifying game files.

    Call only after showing the dependency list and asking for explicit user
    approval. A failed install rolls back new and updated managed JARs.
    """
    profile=profiles.inspect_instance(plan['profile']['root'])
    if profile!=plan['profile']:
        raise ResolutionError('Minecraft profile changed since review; rerun planning.')
    journal=Path(receipts_path)
    old_existed=journal.exists()
    old_rows=profiles.installed_receipts(journal)
    target=Path(inbox)
    target.mkdir(parents=True,exist_ok=True)
    if target.is_symlink():raise ResolutionError('Download folder cannot be a symlink.')
    staged=[]
    for record in plan['dependencies']:
        # A dedicated folder per exact provider version avoids collisions
        # with files users have already downloaded elsewhere.
        home=target/_ident(record['identity'])/_ident(record['version_id'])
        home.mkdir(parents=True,exist_ok=True)
        f=home/record['filename']
        expected=record['hashes']['sha512']
        if f.is_symlink():raise ResolutionError('Dependency download target is a symlink.')
        if f.is_file():
            if _file_sha512(f)!=expected or f.stat().st_size!=record['size']:
                raise ResolutionError('Cached dependency changed; remove it manually before retry.')
            # Reuse only if a matching staged receipt exists.
            matches=[r for r in staging.read_staged(staging_journal)
                     if r.get('archive')==str(f) and r.get('sha256')==staging.file_sha256(f) and
                        r.get('identity')==record['identity'] and r.get('version_id')==record['version_id']]
            if not matches:raise ResolutionError('Dependency exists without a verified stage receipt.')
            staged.append(matches[0])
        else:
            staged_file=staging.stage_download(record,home,staging_journal,downloader=downloader)
            if Path(staged_file).stat().st_size!=record['size'] or _file_sha512(staged_file)!=expected:
                raise ResolutionError('Downloaded dependency hash does not match Modrinth metadata.')
            matches=[r for r in staging.read_staged(staging_journal) if r.get('archive')==str(staged_file)]
            if len(matches)!=1:raise ResolutionError('Dependency staging receipt was not saved.')
            staged.append(matches[0])
    actions=[]
    try:
        for rec in [*staged,plan['parent']]:
            before=profiles.installed_receipts(journal)
            prior=next((r for r in before if r.get('profile')==profile['root'] and
                        r.get('project_id')==rec['identity']),None)
            res=profiles.install_reviewed(rec,profile['root'],journal,recovery_dir)
            actions.append({**res,'hash':rec['sha256'],
                            'old_path':prior.get('installed_path') if prior else ''})
        return {'action':'installed','path':actions[-1]['path'],
                'backup':actions[-1]['backup'],'profile':profile['root'],
                'dependency_count':len(staged)}
    except Exception as exc:
        issues=_recover(actions,journal,old_rows,old_existed)
        if issues:
            raise ResolutionError('Install failed; rollback needs manual attention: '+'; '.join(issues)) from exc
        raise
