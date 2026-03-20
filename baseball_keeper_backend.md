# Baseball Keeper — Backend Architecture Spec

## Overview

Two-layer architecture: a **Python data pipeline** that handles all mechanical
fetching and computation, and a **curatorial YAML** where all human-authored
context (badges, tooltips, cross-references) lives. The HTML dashboard reads
one final merged JSON and never needs to change when new games are added.

---

## File Structure

```
baseball-keeper/
│
├── config/
│   ├── games.yaml          # Master list of all game PKs (MLB + MiLB)
│   └── curation.yaml       # Hand-authored badges, notes, cross-refs (keyed by player ID)
│
├── scripts/
│   ├── fetch_games.py      # Pull box scores from MLB Stats API
│   ├── fetch_war.py        # Scrape career WAR from Baseball Reference
│   ├── rank.py             # Compute ranking scores
│   └── build.py            # Master script: runs everything, outputs players.json
│
├── data/
│   ├── players.json        # Final merged output — what the dashboard reads
│   └── cache/              # Raw API responses cached locally (avoid re-fetching)
│
└── dashboard/
    ├── index.html          # The dashboard (reads players.json, unchanged from v2)
    └── players.json        # Symlink or copy of data/players.json
```

---

## games.yaml

```yaml
mlb:
  - pk: 369155        # May 27 2015  TEX @ CLE
  - pk: 490105        # May 12 2017  HOU @ NYY
  - pk: 633476        # Aug 11 2021  TOR @ LAA
  - pk: 745456        # Apr 15 2022  SFG @ CLE
  - pk: 745588        # Sep 11 2022  STL @ PIT
  - pk: 745601        # Apr  7 2023  SEA @ CLE
  - pk: 745610        # Apr 11 2023  BOS @ TBR
  - pk: 745690        # Jul 21 2024  BOS @ LAD
  - pk: 745700        # Jul 27 2024  SEA @ CWS
  - pk: 745750        # Jun 28 2025  TOR @ BOS
  - pk: 745800        # Aug 17 2025  ATL @ CLE
  - pk: 745810        # Aug 26 2025  KCR @ CWS

milb:
  - pk: 407623        # May  7 2010  Gwinnett @ Syracuse   (Strasburg AAA debut)
  - pk: 408120        # Apr  5 2012  Rochester @ Syracuse  (Harper AAA debut)
  - pk: 550123        # Jul  4 2017  LHV @ Syracuse
  - pk: 550456        # Aug  5 2017  Unknown @ Syracuse
  - pk: 640123        # Apr 12 2022  Buffalo @ Rochester
  - pk: 640456        # Jun  3 2022  Buffalo @ Rochester   (Strasburg rehab)
  - pk: 700123        # Aug 13 2023  Norfolk @ Rochester
  - pk: 720123        # Jun 28 2024  Indianapolis @ Rochester (Wood last AAA game)
  - pk: 750123        # Jul 19 2025  Omaha @ Buffalo       (Rich Hill)
  - pk: 750456        # Aug 15 2025  LHV @ Buffalo         (Bieber rehab)

# NOTE: MiLB PKs above are placeholders — you'll need to look these up.
# Easiest method: https://statsapi.mlb.com/api/v1/schedule?sportId=11&date=YYYY-MM-DD
# sportId=1 = MLB, sportId=11 = AAA, sportId=12 = AA, sportId=13 = A
# Response includes gamePk for every game on that date.
```

---

## fetch_games.py

```python
"""
Fetches box scores for all games in games.yaml using the MLB Stats API.
Resolves full player names and IDs. Caches raw responses locally.
"""

import json, yaml, time, requests
from pathlib import Path

CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://statsapi.mlb.com/api/v1"

def get_boxscore(pk: int) -> dict:
    cache_file = CACHE_DIR / f"boxscore_{pk}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    url = f"{BASE}/game/{pk}/boxscore"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    cache_file.write_text(json.dumps(data, indent=2))
    time.sleep(0.3)  # be polite to the API
    return data

def extract_players(pk: int, level: str) -> list[dict]:
    """
    Returns a list of player appearances from a single game box score.
    Each entry: {player_id, full_name, team, level, game_pk, role}
    role = 'batter' | 'pitcher'
    """
    data = get_boxscore(pk)
    players = []

    for side in ("away", "home"):
        team_data = data["teams"][side]
        team_name = team_data["team"]["name"]

        # Batters
        for pid_str, p in team_data.get("players", {}).items():
            pid = p["person"]["id"]
            name = p["person"]["fullName"]
            stats = p.get("stats", {})

            batting = stats.get("batting", {})
            pitching = stats.get("pitching", {})

            if batting.get("atBats") is not None or batting.get("plateAppearances"):
                players.append({
                    "player_id": pid,
                    "full_name": name,
                    "team": team_name,
                    "level": level,
                    "game_pk": pk,
                    "role": "batter",
                    "stats": {
                        "AB":  batting.get("atBats", 0),
                        "R":   batting.get("runs", 0),
                        "H":   batting.get("hits", 0),
                        "RBI": batting.get("rbi", 0),
                        "BB":  batting.get("baseOnBalls", 0),
                        "SO":  batting.get("strikeOuts", 0),
                        "HR":  batting.get("homeRuns", 0),
                    }
                })

            if pitching.get("inningsPitched") is not None:
                players.append({
                    "player_id": pid,
                    "full_name": name,
                    "team": team_name,
                    "level": level,
                    "game_pk": pk,
                    "role": "pitcher",
                    "stats": {
                        "IP":  pitching.get("inningsPitched", "0"),
                        "H":   pitching.get("hits", 0),
                        "R":   pitching.get("runs", 0),
                        "ER":  pitching.get("earnedRuns", 0),
                        "BB":  pitching.get("baseOnBalls", 0),
                        "SO":  pitching.get("strikeOuts", 0),
                    }
                })

    return players


def fetch_all_appearances(games_config: dict) -> list[dict]:
    all_appearances = []

    for game in games_config.get("mlb", []):
        pk = game["pk"]
        print(f"  Fetching MLB game {pk}...")
        try:
            all_appearances.extend(extract_players(pk, level="MLB"))
        except Exception as e:
            print(f"    ERROR: {e}")

    for game in games_config.get("milb", []):
        pk = game["pk"]
        print(f"  Fetching MiLB game {pk}...")
        try:
            all_appearances.extend(extract_players(pk, level="MiLB"))
        except Exception as e:
            print(f"    ERROR: {e}")

    return all_appearances
```

---

## fetch_war.py

```python
"""
Pulls career WAR and peak season WAR from Baseball Reference.
Uses pybaseball's playerid_lookup as a bridge to get BBRef IDs,
then fetches WAR data. Results cached locally.

pip install pybaseball requests beautifulsoup4
"""

import json, time, requests
from pathlib import Path
from pybaseball import playerid_lookup, batting_stats, pitching_stats

CACHE_DIR = Path("data/cache")
WAR_CACHE = CACHE_DIR / "war_data.json"

def load_war_cache() -> dict:
    if WAR_CACHE.exists():
        return json.loads(WAR_CACHE.read_text())
    return {}

def save_war_cache(data: dict):
    WAR_CACHE.write_text(json.dumps(data, indent=2))

def get_war_for_player(mlb_id: int, full_name: str, war_cache: dict) -> dict:
    """
    Returns {career_war, peak_war, bbref_id} for a player.
    Falls back to 0.0 if not found (minor leaguers, pitchers not in system, etc.)
    """
    key = str(mlb_id)
    if key in war_cache:
        return war_cache[key]

    # Parse name for lookup
    parts = full_name.strip().split()
    last = parts[-1]
    first = parts[0]

    try:
        result = playerid_lookup(last, first)
        if result.empty:
            raise ValueError("not found")

        # Match by MLB ID if possible
        match = result[result["key_mlbam"] == mlb_id]
        if match.empty:
            match = result.iloc[[0]]  # fall back to first result

        bbref_id = match["key_bbref"].values[0]
        time.sleep(0.5)

        # Try batting WAR first, then pitching
        career_war = 0.0
        peak_war = 0.0

        try:
            bdata = batting_stats(1990, 2026, qual=0)
            player_rows = bdata[bdata["IDfg"] == match["key_fangraphs"].values[0]]
            if not player_rows.empty:
                career_war = float(player_rows["WAR"].sum())
                peak_war = float(player_rows["WAR"].max())
        except Exception:
            pass

        if career_war == 0.0:
            try:
                pdata = pitching_stats(1990, 2026, qual=0)
                player_rows = pdata[pdata["IDfg"] == match["key_fangraphs"].values[0]]
                if not player_rows.empty:
                    career_war = float(player_rows["WAR"].sum())
                    peak_war = float(player_rows["WAR"].max())
            except Exception:
                pass

        result_data = {
            "career_war": round(career_war, 1),
            "peak_war": round(peak_war, 1),
            "bbref_id": str(bbref_id)
        }

    except Exception as e:
        print(f"    WAR lookup failed for {full_name} ({mlb_id}): {e}")
        result_data = {"career_war": 0.0, "peak_war": 0.0, "bbref_id": ""}

    war_cache[key] = result_data
    save_war_cache(war_cache)
    return result_data
```

---

## rank.py

```python
"""
Computes a ranking score for each player.

Formula:
    base_score = career_war
    
    # Age correction for players under 28 with under 6 years service
    # Projects their career WAR forward using current rate
    if age < 28 and years_in_mlb < 6:
        base_score = career_war * (28 / max(age, 20))
    
    # Cap the projection so a 22-year-old with 3 WAR
    # doesn't leapfrog a 35-year-old with 50 WAR
    base_score = min(base_score, career_war + 30)
    
    ranking_score = base_score * games_seen

This keeps Ramirez (high WAR × 4 games) legitimately near the top,
gives young stars like Henderson/Wood a modest boost without overcorrecting,
and naturally tanks guys like Straw relative to Pujols.

MiLB-only players (career_war = 0 or very low) rank at the bottom,
which is correct — they're context, not stars.
"""

from datetime import date

def compute_age(birth_year: int) -> int:
    return date.today().year - birth_year

def ranking_score(career_war: float, peak_war: float,
                  games_seen: int, birth_year: int | None,
                  years_in_mlb: int | None) -> float:

    base = career_war

    # Age correction
    if birth_year and years_in_mlb is not None:
        age = compute_age(birth_year)
        if age < 28 and years_in_mlb < 6 and career_war > 0:
            projected = career_war * (28 / max(age, 20))
            projected = min(projected, career_war + 30)  # cap
            base = projected

    return round(base * games_seen, 2)
```

---

## curation.yaml  (the part you maintain forever)

```yaml
# Keyed by MLB Stats API player ID (integer)
# This file is NEVER overwritten by the script — edit freely.
# badge options: 🏛️ ⚠️ 🌟 ⭐ 🏆 🔄 🌱 📖

players:
  # ── Hall of Fame ───────────────────────────────────────────────
  660670:  # Albert Pujols
    badge: "🏛️"
    note: "HOF lock (eligible 2027); 3× MVP; 703 career HRs; hit #697 in your 2022 game"

  425877:  # Adrian Beltre
    badge: "🏛️"
    note: "Hall of Fame 2024; 477 career HRs; played in your 2015 game"

  425784:  # Yadier Molina
    badge: "🏛️"
    note: "9× Gold Glove C; 2× WS champion; strong HOF case, eligible 2027"

  # ── Future HOF / Superstars ────────────────────────────────────
  660271:  # Shohei Ohtani
    badge: "🌟"
    note: "2021 & 2023 AL MVP (both unanimous); 2024 NL MVP; 50-50 season; seen in 2 games"

  592450:  # Aaron Judge
    badge: "🌟"
    note: "2017 AL ROY seen here; 2022 AL MVP (62 HRs); franchise icon"

  518692:  # Jose Ramirez
    badge: "🌟"
    note: "4× Silver Slugger; seen in 4 CLE games across 10 seasons (2015–2025)"
    cross_refs:
      - "MLB: CLE×4 (2015, 2022, 2023, 2025)"

  # ... add all your flagged players here ...

  # ── MiLB-specific entries (no MLB stats) ──────────────────────
  # For players who only appear in MiLB games, career_war will be
  # near 0 or pulled automatically if they have MLB service time.
  # Add notes for context.

  # ── Cross-references ───────────────────────────────────────────
  # Players seen on multiple teams or in both MLB + MiLB
  605113:  # Tyler Clippard
    badge: "🔄"
    note: "Veteran reliever; one of the most-traveled pitchers of his era"
    cross_refs:
      - "MLB: HOU@NYY May 12 2017"
      - "MiLB: Rochester Apr 12 2022"
      - "MiLB: Rochester Jun 3 2022"

milb_game_context:
  # Narrative context for MiLB cards, keyed by game PK
  # The script renders these as the italic description on each card
  407623:  # Strasburg AAA debut
    context: "The most hyped pitching prospect in baseball history makes his AAA debut. This was the launchpad."
  408120:  # Harper AAA debut
    context: "Home opener. Bryce Harper, 19 years old, makes his AAA debut on Opening Day."
  640456:  # Strasburg rehab 2022
    context: "Season-high crowd of 10,510. No-hit bid through 5.2 innings. Three MLB starts later, he never pitched again. This was it."
  # ... add others ...
```

---

## build.py  (the master script you run)

```python
"""
Master build script. Run this whenever you add new games.

Usage:
    python scripts/build.py

Output:
    data/players.json   — ready for the dashboard
"""

import json, yaml
from pathlib import Path
from collections import defaultdict

from fetch_games import fetch_all_appearances
from fetch_war import get_war_for_player, load_war_cache
from rank import ranking_score

# ── Load config ────────────────────────────────────────────────
games_config = yaml.safe_load(Path("config/games.yaml").read_text())
curation = yaml.safe_load(Path("config/curation.yaml").read_text())
player_curation = curation.get("players", {})
milb_context = curation.get("milb_game_context", {})

# ── Fetch all box score appearances ───────────────────────────
print("Fetching box scores...")
appearances = fetch_all_appearances(games_config)

# ── Aggregate by player_id ────────────────────────────────────
# player_id → {full_name, level, games_seen, roles, cumulative_stats}
print("Aggregating player data...")
player_map = defaultdict(lambda: {
    "player_id": None,
    "full_name": "",
    "level": set(),      # {"MLB"} or {"MiLB"} or {"MLB","MiLB"}
    "game_pks": set(),
    "roles": set(),
    "batting": defaultdict(int),
    "pitching": defaultdict(float),
})

for app in appearances:
    pid = app["player_id"]
    pm = player_map[pid]
    pm["player_id"] = pid
    pm["full_name"] = app["full_name"]
    pm["level"].add(app["level"])
    pm["game_pks"].add(app["game_pk"])
    pm["roles"].add(app["role"])

    if app["role"] == "batter":
        for k, v in app["stats"].items():
            pm["batting"][k] += v
    else:
        # IP needs special handling (e.g. "6.1" = 6⅓ innings)
        ip_str = str(app["stats"].get("IP", "0"))
        try:
            w, f = (ip_str.split(".") + ["0"])[:2]
            pm["pitching"]["IP"] += int(w) + int(f) / 3
        except Exception:
            pass
        for k in ("H", "R", "ER", "BB", "SO"):
            pm["pitching"][k] += app["stats"].get(k, 0)

# ── Pull WAR for every player ──────────────────────────────────
print("Fetching WAR data (uses cache after first run)...")
war_cache = load_war_cache()

output_players = []
for pid, pm in player_map.items():
    war_data = get_war_for_player(pid, pm["full_name"], war_cache)
    games_seen = len(pm["game_pks"])

    # Merge curation
    curated = player_curation.get(pid, {})

    # Compute ranking score
    # birth_year and years_in_mlb could be fetched from the API too;
    # for now, set to None and the age correction is skipped.
    score = ranking_score(
        career_war=war_data["career_war"],
        peak_war=war_data["peak_war"],
        games_seen=games_seen,
        birth_year=None,
        years_in_mlb=None,
    )

    # Format IP for display
    ip_raw = pm["pitching"].get("IP", 0)
    ip_whole = int(ip_raw)
    ip_frac = round((ip_raw - ip_whole) * 3)
    ip_display = f"{ip_whole}.{ip_frac}" if ip_frac else str(ip_whole)

    # AVG
    ab = pm["batting"].get("AB", 0)
    h  = pm["batting"].get("H", 0)
    avg = f"{h/ab:.3f}".lstrip("0") if ab > 0 else ".000"

    # ERA
    er  = pm["pitching"].get("ER", 0)
    ip_f = pm["pitching"].get("IP", 0)
    era = f"{er * 9 / ip_f:.2f}" if ip_f > 0 else "—"

    output_players.append({
        "player_id": pid,
        "full_name": pm["full_name"],
        "level": sorted(pm["level"]),        # ["MLB"] or ["MiLB"] or ["MLB","MiLB"]
        "games_seen": games_seen,
        "roles": sorted(pm["roles"]),
        "career_war": war_data["career_war"],
        "peak_war":   war_data["peak_war"],
        "ranking_score": score,

        # batting stats (0 if pitcher-only)
        "AB":  pm["batting"].get("AB", 0),
        "R":   pm["batting"].get("R",  0),
        "H":   pm["batting"].get("H",  0),
        "RBI": pm["batting"].get("RBI",0),
        "BB":  pm["batting"].get("BB", 0),
        "SO_bat": pm["batting"].get("SO", 0),
        "HR":  pm["batting"].get("HR", 0),
        "AVG": avg,

        # pitching stats (blank if batter-only)
        "IP":  ip_display,
        "H_pit":  int(pm["pitching"].get("H",  0)),
        "R_pit":  int(pm["pitching"].get("R",  0)),
        "ER":  int(pm["pitching"].get("ER", 0)),
        "BB_pit": int(pm["pitching"].get("BB", 0)),
        "SO_pit": int(pm["pitching"].get("SO", 0)),
        "ERA": era,

        # curation layer
        "badge":      curated.get("badge", ""),
        "note":       curated.get("note", ""),
        "cross_refs": curated.get("cross_refs", []),

        # MiLB flag
        "milb_only": pm["level"] == {"MiLB"},
        "seen_in_milb": "MiLB" in pm["level"],
    })

# ── Sort by ranking score descending ──────────────────────────
output_players.sort(key=lambda p: p["ranking_score"], reverse=True)

# ── Write output ───────────────────────────────────────────────
out_path = Path("data/players.json")
out_path.write_text(json.dumps(output_players, indent=2))
print(f"\nDone. {len(output_players)} players written to {out_path}")
print(f"Top 10 by ranking score:")
for p in output_players[:10]:
    print(f"  {p['full_name']:30} score={p['ranking_score']:8.1f}  "
          f"WAR={p['career_war']:6.1f}  G={p['games_seen']}")
```

---

## Finding MiLB Game PKs

The MLB Stats API covers MiLB games. Use `sportId` to filter by level:

```
MLB:  sportId=1
AAA:  sportId=11
AA:   sportId=12
A+:   sportId=13
A:    sportId=14
```

To find a game PK for a specific date:
```
https://statsapi.mlb.com/api/v1/schedule?sportId=11&date=2022-06-03
```

Response includes `gamePk` for every AAA game that day. Filter by team name
to find the right one. The PKs in `games.yaml` above are **placeholders** —
you'll need to look up the real ones for each MiLB date before the first run.

---

## Dependencies

```
pip install requests pyyaml pybaseball
```

pybaseball handles the BBRef/FanGraphs ID bridging. The MLB Stats API requires
no authentication and no API key.

---

## What the dashboard needs to change

Very little. The dashboard currently reads hardcoded JS data. After migration:
1. Load `players.json` via `fetch()` instead of hardcoded `const DATA = {...}`
2. Add a `ranking_score` sort column alongside AB and IP
3. Add a `milb_only` row style (slightly muted) and `seen_in_milb` badge chip
4. The MiLB cards tab stays hand-authored in `curation.yaml` — no change needed

Everything else (tooltips, badges, filters, cross-refs) maps 1:1 to the new
JSON structure.
