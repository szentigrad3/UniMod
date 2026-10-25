"""Read-only preview of existing Prism/MultiMC Minecraft profiles.

No imports, copies, config changes, launcher writes, or network requests.
Original UniMod implementation; existing minecraft_profiles scanner is authoritative.
"""
from pathlib import Path

import minecraft_profiles

MAX_MOD_ENTRIES = 5000


def _mod_counts(mods_path):
    """Count ordinary JARs only; never open archives or traverse links."""
    mods = Path(mods_path)
    if not mods.is_dir() or mods.is_symlink():
        return 0, 0, 'Mods directory unavailable or unsafe'
    enabled = disabled = 0
    try:
        with mods.iterdir() as entries:
            for index, item in enumerate(entries):
                if index >= MAX_MOD_ENTRIES:
                    return enabled, disabled, 'Too many entries to inspect completely'
                if item.is_symlink() or not item.is_file():
                    continue
                low = item.name.casefold()
                if low.endswith('.jar'):
                    enabled += 1
                elif low.endswith('.jar.disabled'):
                    disabled += 1
    except OSError:
        return enabled, disabled, 'Cannot read some mods'
    return enabled, disabled, None


def preview(home=None):
    """List detected Minecraft instances with an informational count.

    The returned paths are for internal selection only: do not include them in
    any copyable report. Detection alone never establishes import eligibility.
    """
    rows = []
    for entry in minecraft_profiles.discover_instances(home=home):
        enabled, disabled, warning = _mod_counts(entry['mods'])
        rows.append({
            'manager': 'Prism / MultiMC',
            'instance_root': entry['root'],
            'minecraft_version': entry['version'],
            'loader': entry['loader'],
            'loader_version': entry['loader_version'],
            'enabled_jars': enabled,
            'disabled_jars': disabled,
            'warning': warning,
            'action': 'Review only — not imported',
        })
    return rows


def safe_summary(rows):
    """Aggregate counts only, excluding paths, names, tokens and IDs."""
    if not isinstance(rows, list):
        raise ValueError('Invalid preview')
    if len(rows) > 1000:
        raise ValueError('Too many profiles')
    count = sum(1 for row in rows if isinstance(row, dict))
    enabled = sum(min(MAX_MOD_ENTRIES, max(0, int(row.get('enabled_jars', 0))))
                  for row in rows if isinstance(row, dict))
    disabled = sum(min(MAX_MOD_ENTRIES, max(0, int(row.get('disabled_jars', 0))))
                   for row in rows if isinstance(row, dict))
    return ('UniMod profile discovery (read-only preview)\n'
            f'Recognized Prism/MultiMC instances: {count}\n'
            f'Enabled JAR files: {enabled}\n'
            f'Disabled JAR files: {disabled}\n'
            'No profiles or mods were imported or modified.\n'
            'Counts do not establish mod identity, safety or compatibility.\n')
