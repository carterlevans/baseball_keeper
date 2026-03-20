"""
fetch_statcast.py
-----------------
Downloads Baseball Savant / Statcast CSV for each MLB game attended,
caches the raw CSV, and extracts superlatives:

  - Farthest home run (ft)
  - Hardest exit velocity (mph)
  - Fastest pitch (mph)
  - Highest spin rate (RPM)
  - Most movement on a single pitch (inches, total)

Writes:
  data/statcast_superlatives.json   (source of truth)
  dashboard/statcast_superlatives.json  (copy for the dashboard)

Usage:
  python scripts/fetch_statcast.py
"""

import csv
import io
import json
import math
import time
from pathlib import Path

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
GAMES_JSON  = ROOT / "dashboard" / "games.json"
CACHE_DIR   = ROOT / "data" / "cache" / "statcast"
OUT_DATA    = ROOT / "data" / "statcast_superlatives.json"
OUT_DASH    = ROOT / "dashboard" / "statcast_superlatives.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── Build pitcher ID→name lookup from cached gamecard JSONs ──────────────────
def build_pitcher_lookup():
    """Walk all cached gamecard_{pk}.json files and map player ID → fullName."""
    lookup = {}
    for f in (ROOT / "data" / "cache").glob("gamecard_*.json"):
        try:
            data = json.loads(f.read_text())
            ld   = data.get("liveData", {})
            for side in ("away", "home"):
                players = ld.get("boxscore", {}).get("teams", {}).get(side, {}).get("players", {})
                for key, p in players.items():
                    pid  = p.get("person", {}).get("id")
                    name = p.get("person", {}).get("fullName")
                    if pid and name:
                        lookup[str(pid)] = name
        except Exception:
            pass
    return lookup

PITCHER_NAMES = build_pitcher_lookup()

SAVANT_URL = (
    "https://baseballsavant.mlb.com/statcast_search/csv"
    "?all=true&type=details&game_pk={pk}"
)

# ── Fetch / cache ──────────────────────────────────────────────────────────────
def fetch_csv(pk: int) -> str:
    cache = CACHE_DIR / f"statcast_{pk}.csv"
    if cache.exists():
        print(f"  [cache] {pk}")
        return cache.read_text(encoding="utf-8")

    url = SAVANT_URL.format(pk=pk)
    print(f"  [fetch] {pk} → {url}")
    resp = requests.get(url, timeout=60, headers={"User-Agent": "baseball-keeper/1.0"})
    resp.raise_for_status()
    cache.write_text(resp.text, encoding="utf-8")
    time.sleep(1.5)   # be polite to Savant
    return resp.text


# ── Safe numeric helpers ───────────────────────────────────────────────────────
def fnum(val):
    try:
        v = float(val)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError):
        return None


def total_break_inches(row):
    """Total pitch movement in inches using modern API break fields.
    Falls back to pfx_x/pfx_z (in feet → inches) for older data."""
    x = fnum(row.get("api_break_x_batter_in"))
    z = fnum(row.get("api_break_z_with_gravity"))
    if x is not None and z is not None:
        return round(math.sqrt(x**2 + z**2), 1)
    # Older data: pfx_x/pfx_z in feet
    x = fnum(row.get("pfx_x"))
    z = fnum(row.get("pfx_z"))
    if x is None or z is None:
        return None
    return round(math.sqrt(x**2 + z**2) * 12, 1)

def pitcher_name(row):
    """Resolve pitcher name: prefer our gamecard lookup, fall back to batter field."""
    pid = row.get("pitcher", "")
    return PITCHER_NAMES.get(str(pid)) or row.get("player_name", "Unknown")

def clean_col(row, key):
    """Handle BOM-prefixed first column key."""
    return row.get(key) or row.get("\ufeff" + key) or row.get(f'\ufeff"{key}"', "")


# ── Superlative extraction for one game ───────────────────────────────────────
def extract_game(pk, game_meta):
    try:
        raw = fetch_csv(pk)
    except Exception as e:
        print(f"  ✗ fetch failed for {pk}: {e}")
        return None

    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        print(f"  ✗ empty CSV for {pk}")
        return None

    label = f"{game_meta['away_abbr']} @ {game_meta['home_abbr']}"

    result = {
        "pk":    pk,
        "label": label,
        "date":  game_meta["date"],
    }

    # ── Farthest home run ──────────────────────────────────────────────────────
    hrs = [r for r in rows
           if r.get("events") == "home_run" and fnum(r.get("hit_distance_sc"))]
    if hrs:
        best = max(hrs, key=lambda r: fnum(r["hit_distance_sc"]))
        result["farthest_hr"] = {
            "distance_ft": int(fnum(best["hit_distance_sc"])),
            "batter":      best.get("player_name", "Unknown"),
            "exit_velo":   fnum(best.get("launch_speed")),
            "launch_angle":fnum(best.get("launch_angle")),
        }

    # ── Hardest exit velocity (any batted ball in play) ───────────────────────
    batted = [r for r in rows if fnum(r.get("launch_speed"))
              and r.get("type") == "X"]          # X = batted ball
    if batted:
        best = max(batted, key=lambda r: fnum(r["launch_speed"]))
        result["hardest_hit"] = {
            "exit_velo_mph": round(fnum(best["launch_speed"]), 1),
            "batter":        best.get("player_name", "Unknown"),
            "events":        best.get("events", "").replace("_", " "),
        }

    # ── Fastest pitch ─────────────────────────────────────────────────────────
    pitches = [r for r in rows if fnum(r.get("release_speed"))]
    if pitches:
        best = max(pitches, key=lambda r: fnum(r["release_speed"]))
        result["fastest_pitch"] = {
            "speed_mph":  round(fnum(best["release_speed"]), 1),
            "pitcher":    pitcher_name(best),
            "pitch_name": best.get("pitch_name", "").strip() or clean_col(best, "pitch_type"),
        }

    # ── Highest spin rate ─────────────────────────────────────────────────────
    spinnable = [r for r in rows if fnum(r.get("release_spin_rate"))]
    if spinnable:
        best = max(spinnable, key=lambda r: fnum(r["release_spin_rate"]))
        result["most_spin"] = {
            "spin_rpm":   int(fnum(best["release_spin_rate"])),
            "pitcher":    pitcher_name(best),
            "pitch_name": best.get("pitch_name", "").strip() or clean_col(best, "pitch_type"),
        }

    # ── Most movement on a single pitch ───────────────────────────────────────
    moveable = [r for r in rows if total_break_inches(r) is not None]
    if moveable:
        best = max(moveable, key=total_break_inches)
        result["most_break"] = {
            "break_in":   total_break_inches(best),
            "pitcher":    pitcher_name(best),
            "pitch_name": best.get("pitch_name", "").strip() or clean_col(best, "pitch_type"),
        }

    return result


# ── Roll up overall bests across all games ────────────────────────────────────
def overall_bests(game_results):
    overall = {}

    def update(key, game, get_val, higher_is_better=True):
        val = get_val(game.get(key))
        if val is None:
            return
        prev = overall.get(key)
        if prev is None or (higher_is_better and val > prev["_val"]) \
                        or (not higher_is_better and val < prev["_val"]):
            overall[key] = {**game[key], "_val": val,
                            "game": game["label"], "date": game["date"]}

    for g in game_results:
        update("farthest_hr",  g, lambda x: x and x.get("distance_ft"))
        update("hardest_hit",  g, lambda x: x and x.get("exit_velo_mph"))
        update("fastest_pitch",g, lambda x: x and x.get("speed_mph"))
        update("most_spin",    g, lambda x: x and x.get("spin_rpm"))
        update("most_break",   g, lambda x: x and x.get("break_in"))

    # Strip internal _val keys
    return {k: {ik: iv for ik, iv in v.items() if ik != "_val"}
            for k, v in overall.items()}


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    games = json.loads(GAMES_JSON.read_text())
    mlb   = [g for g in games if g.get("level") == "MLB"]

    print(f"Processing {len(mlb)} MLB games…\n")

    game_results = []
    for g in mlb:
        pk = g["pk"]
        print(f"→ {g['date']}  {g['away_abbr']} @ {g['home_abbr']}  (pk={pk})")
        res = extract_game(pk, g)
        if res:
            game_results.append(res)
            # Quick summary
            if res.get("farthest_hr"):
                hr = res["farthest_hr"]
                print(f"   HR  {hr['batter']} — {hr['distance_ft']} ft")
            if res.get("hardest_hit"):
                hh = res["hardest_hit"]
                print(f"   EV  {hh['batter']} — {hh['exit_velo_mph']} mph ({hh['events']})")
            if res.get("fastest_pitch"):
                fp = res["fastest_pitch"]
                print(f"   FB  {fp['pitcher']} — {fp['speed_mph']} mph ({fp['pitch_name']})")
        print()

    bests = overall_bests(game_results)

    output = {"overall": bests, "games": {str(g["pk"]): g for g in game_results}}

    OUT_DATA.write_text(json.dumps(output, indent=2))
    OUT_DASH.write_text(json.dumps(output, indent=2))

    print("─" * 60)
    print("Overall bests:")
    for key, val in bests.items():
        print(f"  {key}: {val}")

    print(f"\n✓ Written to {OUT_DATA}")
    print(f"✓ Written to {OUT_DASH}")


if __name__ == "__main__":
    main()
