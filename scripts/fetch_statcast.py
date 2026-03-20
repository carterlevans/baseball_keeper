"""
fetch_statcast.py
-----------------
Downloads Baseball Savant / Statcast CSV for each MLB game attended,
caches the raw CSV, and builds ranked top-10 lists for:

  - Farthest home run (ft)
  - Hardest exit velocity (mph)
  - Fastest pitch (mph)
  - Highest spin rate (RPM)
  - Most total pitch movement (inches)

Writes:
  data/statcast_superlatives.json       (source of truth)
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

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).resolve().parent.parent
GAMES_JSON = ROOT / "dashboard" / "games.json"
CACHE_DIR  = ROOT / "data" / "cache" / "statcast"
OUT_DATA   = ROOT / "data" / "statcast_superlatives.json"
OUT_DASH   = ROOT / "dashboard" / "statcast_superlatives.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)

SAVANT_URL = (
    "https://baseballsavant.mlb.com/statcast_search/csv"
    "?all=true&type=details&game_pk={pk}"
)

# ── Build pitcher ID → name from cached gamecard JSONs ────────────────────────
def build_pitcher_lookup():
    lookup = {}
    for f in (ROOT / "data" / "cache").glob("gamecard_*.json"):
        try:
            ld = json.loads(f.read_text()).get("liveData", {})
            for side in ("away", "home"):
                for p in ld.get("boxscore", {}).get("teams", {}).get(side, {}).get("players", {}).values():
                    pid  = p.get("person", {}).get("id")
                    name = p.get("person", {}).get("fullName")
                    if pid and name:
                        lookup[str(pid)] = name
        except Exception:
            pass
    return lookup

PITCHER_NAMES = build_pitcher_lookup()

# ── Numeric helpers ────────────────────────────────────────────────────────────
def fnum(val):
    try:
        v = float(val)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError):
        return None

def total_break_inches(row):
    """Modern api_break fields (in inches); fall back to pfx (feet → inches)."""
    x = fnum(row.get("api_break_x_batter_in"))
    z = fnum(row.get("api_break_z_with_gravity"))
    if x is not None and z is not None:
        return round(math.sqrt(x**2 + z**2), 1)
    x = fnum(row.get("pfx_x"))
    z = fnum(row.get("pfx_z"))
    if x is None or z is None:
        return None
    return round(math.sqrt(x**2 + z**2) * 12, 1)

def pitcher_name(row):
    pid = row.get("pitcher", "")
    return PITCHER_NAMES.get(str(pid)) or "Unknown"

def flip_name(s):
    """'Last, First' → 'First Last'"""
    if not s:
        return s
    parts = s.split(",", 1)
    return f"{parts[1].strip()} {parts[0].strip()}" if len(parts) == 2 else s

# ── Fetch / cache CSV ──────────────────────────────────────────────────────────
def fetch_csv(pk):
    cache = CACHE_DIR / f"statcast_{pk}.csv"
    if cache.exists():
        print(f"  [cache] {pk}")
        return cache.read_text(encoding="utf-8")
    url = SAVANT_URL.format(pk=pk)
    print(f"  [fetch] {pk}")
    resp = requests.get(url, timeout=60, headers={"User-Agent": "baseball-keeper/1.0"})
    resp.raise_for_status()
    cache.write_text(resp.text, encoding="utf-8")
    time.sleep(1.5)
    return resp.text

# ── Extract all events from one game ──────────────────────────────────────────
def extract_events(pk, game_meta):
    try:
        raw = fetch_csv(pk)
    except Exception as e:
        print(f"  ✗ {pk}: {e}")
        return None

    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        print(f"  ✗ empty CSV for {pk}")
        return None

    label = f"{game_meta['away_abbr']} @ {game_meta['home_abbr']}"
    date  = game_meta["date"]

    hrs, batted, pitches = [], [], []

    for r in rows:
        # ── Home runs ──────────────────────────────────────────────────────────
        if r.get("events") == "home_run" and fnum(r.get("hit_distance_sc")):
            hrs.append({
                "batter":       flip_name(r.get("player_name", "")),
                "distance_ft":  int(fnum(r["hit_distance_sc"])),
                "exit_velo":    round(fnum(r["launch_speed"]), 1) if fnum(r.get("launch_speed")) else None,
                "launch_angle": round(fnum(r["launch_angle"]), 1) if fnum(r.get("launch_angle")) else None,
                "game": label, "date": date,
            })

        # ── Batted balls (any) ─────────────────────────────────────────────────
        if r.get("type") == "X" and fnum(r.get("launch_speed")):
            batted.append({
                "batter":       flip_name(r.get("player_name", "")),
                "exit_velo_mph": round(fnum(r["launch_speed"]), 1),
                "result":        r.get("events", "").replace("_", " ").title() or "—",
                "game": label, "date": date,
            })

        # ── Pitches ────────────────────────────────────────────────────────────
        spd  = fnum(r.get("release_speed"))
        spin = fnum(r.get("release_spin_rate"))
        brk  = total_break_inches(r)
        if spd or spin or brk:
            pname = pitcher_name(r)
            ptype = r.get("pitch_name", "").strip() or r.get("pitch_type", "").strip()
            base  = {"pitcher": pname, "pitch_name": ptype, "game": label, "date": date}
            if spd:
                pitches.append({**base, "_cat": "speed",  "speed_mph": round(spd, 1)})
            if spin:
                pitches.append({**base, "_cat": "spin",   "spin_rpm": int(spin)})
            if brk:
                pitches.append({**base, "_cat": "break",  "break_in": brk})

    print(f"   {len(hrs)} HRs  |  {len(batted)} batted balls  |  {len(pitches)} pitch rows")
    return {"hrs": hrs, "batted": batted, "pitches": pitches}


# ── Build top-10 lists across all games ───────────────────────────────────────
def build_top10(all_events):
    all_hrs    = []
    all_batted = []
    speed_rows = []
    spin_rows  = []
    break_rows = []

    for ev in all_events:
        all_hrs.extend(ev["hrs"])
        all_batted.extend(ev["batted"])
        for p in ev["pitches"]:
            if p["_cat"] == "speed": speed_rows.append(p)
            elif p["_cat"] == "spin":  spin_rows.append(p)
            elif p["_cat"] == "break": break_rows.append(p)

    def top10_dedup(rows, key, dedup_field, reverse=True):
        """Sort by key, then keep only the best entry per unique dedup_field value."""
        ranked = sorted(rows, key=lambda x: x[key], reverse=reverse)
        seen, result = set(), []
        for r in ranked:
            uid = r.get(dedup_field, "")
            if uid not in seen:
                seen.add(uid)
                result.append({k: v for k, v in r.items() if k != "_cat"})
            if len(result) == 10:
                break
        return result

    return {
        "farthest_hr":   top10_dedup(all_hrs,    "distance_ft",  "batter"),
        "hardest_hit":   top10_dedup(all_batted, "exit_velo_mph","batter"),
        "fastest_pitch": top10_dedup(speed_rows, "speed_mph",    "pitcher"),
        "most_spin":     top10_dedup(spin_rows,  "spin_rpm",     "pitcher"),
        "most_break":    top10_dedup(break_rows, "break_in",     "pitcher"),
    }


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    games = json.loads(GAMES_JSON.read_text())
    mlb   = [g for g in games if g.get("level") == "MLB"]

    print(f"Processing {len(mlb)} MLB games…\n")

    all_events = []
    for g in mlb:
        print(f"→ {g['date']}  {g['away_abbr']} @ {g['home_abbr']}")
        ev = extract_events(g["pk"], g)
        if ev:
            all_events.append(ev)
        print()

    top10 = build_top10(all_events)

    # Derive overall bests from position #1 of each list (carousel cards)
    overall = {}
    keys_map = {
        "farthest_hr":   ("farthest_hr",  None),
        "hardest_hit":   ("hardest_hit",  None),
        "fastest_pitch": ("fastest_pitch",None),
        "most_spin":     ("most_spin",    None),
        "most_break":    ("most_break",   None),
    }
    for k in top10:
        if top10[k]:
            overall[k] = top10[k][0]

    output = {"overall": overall, "top10": top10}

    OUT_DATA.write_text(json.dumps(output, indent=2))
    OUT_DASH.write_text(json.dumps(output, indent=2))

    print("─" * 60)
    print("Top 10 counts:")
    for k, lst in top10.items():
        print(f"  {k}: {len(lst)} entries")
    print(f"\n✓ {OUT_DATA}")
    print(f"✓ {OUT_DASH}")


if __name__ == "__main__":
    main()
