"""Read-only provenance for Mod Organizer 2 Nexus archive sidecars.

A sidecar is *untrusted local data*, not proof of publisher authenticity.
The archive is still required to contain a SMAPI ID matching an installed mod;
the user must review source suggestions before saving them.
"""
import configparser
from pathlib import Path
import re

IDENT = re.compile(r"[1-9][0-9]{0,11}\Z")
MAX_BYTES = 32768
GAME_ALIASES = {
    "stardewvalley": {"stardewvalley", "stardew valley", "stardew_valley", "stardew-valley"},
    "graveyardkeeper": {"graveyardkeeper", "graveyard keeper", "graveyard_keeper", "graveyard-keeper"},
    "graveyardkeeper2": {"graveyardkeeper2", "graveyard keeper 2", "graveyard_keeper_2", "graveyard-keeper-2"},
}

def read_mo2_sidecar(archive, expected_domain="stardewvalley"):
    """Return exact Nexus IDs or None. Fail closed for symlinks, mismatched games and malformed files."""
    if expected_domain not in GAME_ALIASES:
        return None
    archive = Path(archive)
    sidecar = archive.with_name(archive.name + ".meta")
    try:
        if not archive.is_file() or archive.is_symlink() or sidecar.is_symlink() or not sidecar.is_file():
            return None
        if sidecar.stat().st_size > MAX_BYTES:
            return None
        raw = sidecar.read_text(encoding="utf-8-sig")
        parser = configparser.ConfigParser(interpolation=None, strict=True)
        parser.read_string(raw)
        if not parser.has_section("General"):
            return None
        meta = parser["General"]
        game_name = meta.get("gameName", "").strip().casefold()
        if game_name not in GAME_ALIASES[expected_domain]:
            return None
        mod_id, file_id = meta.get("modID", "").strip(), meta.get("fileID", "").strip()
        if not (IDENT.fullmatch(mod_id) and IDENT.fullmatch(file_id)):
            return None
        return {"mod_id": mod_id, "file_id": file_id,
                "url": f"https://www.nexusmods.com/{expected_domain}/mods/{mod_id}"}
    except (OSError, UnicodeError, ValueError, configparser.Error):
        return None
