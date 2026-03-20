"""
Pulls career WAR and peak season WAR from Baseball Reference via pybaseball.
Matches on MLB ID directly — no name matching needed.
Downloads the full bat/pitch WAR tables once per run, then caches results.

pip install pybaseball
"""

import json
import time
import requests
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
WAR_CACHE    = CACHE_DIR / "war_data.json"
CAREER_CACHE = CACHE_DIR / "career_stats.json"

BASE = "https://statsapi.mlb.com/api/v1"

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

    # Always check both tables and sum — pitchers who batted (NL/pre-DH)
    # have non-zero batting WAR that would otherwise swallow their pitching WAR.
    # Summing is also correct for two-way players like Ohtani.
    try:
        bat = _get_bwar_bat()
        rows = bat[bat["mlb_ID"] == float(mlb_id)]
        if not rows.empty:
            bbref_id = str(rows["player_ID"].values[0])
            career_war += float(rows["WAR"].sum())
            peak_war = max(peak_war, float(rows["WAR"].nlargest(3).sum()))
    except Exception as e:
        print(f"    Batting WAR lookup failed for {full_name}: {e}")

    try:
        pit = _get_bwar_pitch()
        rows = pit[pit["mlb_ID"] == float(mlb_id)]
        if not rows.empty:
            if not bbref_id:
                bbref_id = str(rows["player_ID"].values[0])
            career_war += float(rows["WAR"].sum())
            peak_war = max(peak_war, float(rows["WAR"].nlargest(3).sum()))
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


# ── Career SP/RP classification ────────────────────────────────

def load_career_cache() -> dict:
    if CAREER_CACHE.exists():
        return json.loads(CAREER_CACHE.read_text())
    return {}


def save_career_cache(data: dict):
    CAREER_CACHE.write_text(json.dumps(data, indent=2))


def get_pitcher_role(mlb_id: int, career_cache: dict) -> str:
    """
    Returns 'starter' or 'reliever' based on career GS/G ratio from
    the MLB Stats API. A player with GS/G > 0.5 over their career is
    a starter — consistent with how BBRef/JAWS classifies them.
    """
    key = str(mlb_id)
    if key in career_cache:
        return career_cache[key]

    role = "reliever"  # default
    try:
        url = (f"{BASE}/people/{mlb_id}"
               f"?hydrate=stats(group=[pitching],type=[career])")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(0.2)

        for stat_block in data.get("people", [{}])[0].get("stats", []):
            if stat_block.get("type", {}).get("displayName") != "career":
                continue
            splits = stat_block.get("splits", [])
            if not splits:
                continue
            s = splits[0]["stat"]
            g  = s.get("gamesPitched", 0) or 0
            gs = s.get("gamesStarted", 0) or 0
            if g > 0 and gs / g > 0.5:
                role = "starter"
            break
    except Exception as e:
        print(f"    Career stats lookup failed for {mlb_id}: {e}")

    career_cache[key] = role
    save_career_cache(career_cache)
    return role
