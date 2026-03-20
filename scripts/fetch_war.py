"""
Pulls career WAR and peak season WAR from Baseball Reference via pybaseball.
Matches on MLB ID directly — no name matching needed.
Downloads the full bat/pitch WAR tables once per run, then caches results.

pip install pybaseball
"""

import json
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
WAR_CACHE = CACHE_DIR / "war_data.json"

# Module-level: download once per build run
_bwar_bat = None
_bwar_pitch = None


def load_war_cache() -> dict:
    if WAR_CACHE.exists():
        return json.loads(WAR_CACHE.read_text())
    return {}


def save_war_cache(data: dict):
    WAR_CACHE.write_text(json.dumps(data, indent=2))


def _get_bwar_bat():
    global _bwar_bat
    if _bwar_bat is None:
        from pybaseball import bwar_bat
        print("  Downloading BBRef batting WAR table (one-time)...")
        _bwar_bat = bwar_bat(return_all=True)
    return _bwar_bat


def _get_bwar_pitch():
    global _bwar_pitch
    if _bwar_pitch is None:
        from pybaseball import bwar_pitch
        print("  Downloading BBRef pitching WAR table (one-time)...")
        _bwar_pitch = bwar_pitch(return_all=True)
    return _bwar_pitch


def get_war_for_player(mlb_id: int, full_name: str, war_cache: dict) -> dict:
    """
    Returns {career_war, peak_war, bbref_id} for a player.
    Falls back to 0.0 if not found (minor leaguers, etc.)
    """
    key = str(mlb_id)
    if key in war_cache:
        return war_cache[key]

    career_war = 0.0
    peak_war = 0.0
    bbref_id = ""

    try:
        bat = _get_bwar_bat()
        rows = bat[bat["mlb_ID"] == float(mlb_id)]
        if not rows.empty:
            bbref_id = str(rows["player_ID"].values[0])
            career_war = float(rows["WAR"].sum())
            peak_war = float(rows["WAR"].max())
    except Exception as e:
        print(f"    Batting WAR lookup failed for {full_name}: {e}")

    if career_war == 0.0:
        try:
            pit = _get_bwar_pitch()
            rows = pit[pit["mlb_ID"] == float(mlb_id)]
            if not rows.empty:
                bbref_id = str(rows["player_ID"].values[0])
                career_war = float(rows["WAR"].sum())
                peak_war = float(rows["WAR"].max())
        except Exception as e:
            print(f"    Pitching WAR lookup failed for {full_name}: {e}")

    result_data = {
        "career_war": round(career_war, 1),
        "peak_war": round(peak_war, 1),
        "bbref_id": bbref_id,
    }

    war_cache[key] = result_data
    save_war_cache(war_cache)
    return result_data
