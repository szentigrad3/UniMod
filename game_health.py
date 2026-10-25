"""Compact, read-only game health summary built from UniMod's existing audits.

Ideas are informed by CKAN dependency checks, Limo staging, Gale onboarding,
and Prism's per-instance compatibility model. This is original UniMod code.
The exported text deliberately includes no local paths, account IDs or URLs.
"""
from collections import Counter

_DEP_WARNINGS = frozenset({
    'Missing', 'Disabled provider', 'Below minimum',
    'Ambiguous providers', 'Version unverified',
})
_MAX_ROWS = 50000


def summarize(game, health, issues, dependencies):
    """Summarize existing scan results; do not touch disk or change mods."""
    if not isinstance(game, dict) or not isinstance(health, dict):
        raise ValueError('Choose a supported installed game first.')
    if not isinstance(issues, list) or not isinstance(dependencies, list):
        raise ValueError('The scan returned invalid results.')
    if len(issues) > _MAX_ROWS or len(dependencies) > _MAX_ROWS:
        raise ValueError('The audit has too many results to summarize.')
    counts = Counter(
        str(item.get('type') or 'Other issue')[:100]
        for item in issues if isinstance(item, dict)
    )
    # Count SMAPI's richer dependency evidence rather than making assumptions
    # about DLL files. Game/SMAPI-provided dependencies may appear missing.
    risk = (sum(
        1 for item in dependencies if isinstance(item, dict)
        and item.get('required') is True
        and item.get('mod_enabled') is True
        and item.get('status') in _DEP_WARNINGS
    ) if game.get('kind') == 'smapi' else 0)
    duplicates = counts['Duplicate enabled ID']
    unmanaged = max(0, int(health.get('unmanaged') or 0))
    total = max(0, int(health.get('folders') or 0))
    enabled = max(0, int(health.get('enabled_folders') or 0))
    # These count different diagnostic types; never add them into a bogus
    # global number of 'broken mods'.
    notes = [
        ('Duplicate mod IDs', duplicates,
         'Multiple enabled SMAPI packages claim the same ID. Review before updating.'),
        ('Dependencies needing review', risk,
         'Missing, disabled, mismatched or uncertain dependencies; check built-in providers too.'),
        ('Packages without reliable metadata', unmanaged,
         'These remain visible, but provider updates should not be inferred from filenames.'),
    ]
    kind = str(game.get('kind') or '')
    if kind != 'smapi':
        notes[0] = ('Duplicate SMAPI IDs', 0, 'Not checked for this game type.')
        notes[1] = ('SMAPI dependencies', 0, 'Not checked for this game type.')
    status = ('Needs review' if duplicates or risk or unmanaged
              else 'No issues found in supported checks')
    return {
        'kind': kind if kind in ('smapi', 'bepinex', 'melonloader', 'generic') else 'other',
        'status': status,
        'packages': total,
        'enabled': enabled,
        'duplicates': duplicates,
        'dependencies': risk,
        'unmanaged': unmanaged,
        'notes': notes,
        'limited': kind != 'smapi',
    }


def safe_report(result):
    """Copyable counts and next steps; omit game paths, names and mod IDs."""
    if not isinstance(result, dict):
        raise ValueError('Invalid health report.')
    def count(name):
        value = result.get(name, 0)
        if type(value) is not int or not 0 <= value <= _MAX_ROWS:
            return 0
        return value
    state = result.get('status')
    state = state if state in (
        'Needs review', 'No issues found in supported checks') else 'Not verified'
    kind = result.get('kind') if result.get('kind') in (
        'smapi','bepinex','melonloader','generic','other') else 'other'
    return (
        'UniMod — Check My Mods (v0.56 development)\n'
        'Game format: ' + kind.upper() + '\n'
        'Installed packages/folders: ' + str(count('packages')) + '\n'
        'Enabled packages/folders: ' + str(count('enabled')) + '\n'
        'Duplicate enabled SMAPI IDs: ' + str(count('duplicates')) + '\n'
        'Required dependencies needing review: ' + str(count('dependencies')) + '\n'
        'Packages without reliable metadata: ' + str(count('unmanaged')) + '\n'
        'Health: ' + state + '\n'
        'All checks were read-only. Missing dependencies may be game-provided.\n'
        'These checks do not guarantee compatibility or successful game launch.\n'
        'Privacy: local paths, mod names, source URLs and credentials omitted.\n'
    )
