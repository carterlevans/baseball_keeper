"""
Master build script. Run from the project root:

    python scripts/build.py

Output: data/players.json
"""

import json
import sys
import yaml
from pathlib import Path
from collections import defaultdict

# Allow imports from scripts/
sys.path.insert(0, str(Path(__file__).parent))

from fetch_games import fetch_all_appearances
from fetch_war import get_war_for_player, load_war_cache, get_pitcher_role, load_career_cache
from rank import ranking_score

ROOT = Path(__file__).parent.parent

# ── Load config ─────────────────────────────────────────────────
games_config = yaml.safe_load((ROOT / "config" / "games.yaml").read_text())
curation = yaml.safe_load((ROOT / "config" / "curation.yaml").read_text())
player_curation = curation.get("players", {}) or {}
milb_context = curation.get("milb_game_context", {}) or {}

# ── Fetch all box score appearances ─────────────────────────────
print("Fetching box scores...")
appearances = fetch_all_appearances(games_config)
print(f"  {len(appearances)} total player-game appearances")

# ── Aggregate by player_id ───────────────────────────────────────
print("Aggregating player data...")
player_map = defaultdict(lambda: {
    "player_id": None,
    "full_name": "",
    "level": set(),
    "game_pks": set(),
    "roles": set(),
    "ever_started": False,
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
    if app.get("game_started"):
        pm["ever_started"] = True

    if app["role"] == "batter":
        for k, v in app["stats"].items():
            pm["batting"][k] += v
    else:
        ip_str = str(app["stats"].get("IP", "0"))
        try:
            parts = ip_str.split(".")
            whole = int(parts[0])
            frac = int(parts[1]) if len(parts) > 1 else 0
            pm["pitching"]["IP"] += whole + frac / 3
        except Exception:
            pass
        for k in ("H", "R", "ER", "BB", "SO"):
            pm["pitching"][k] += app["stats"].get(k, 0)

# ── Pull WAR for every player ────────────────────────────────────
print("Fetching WAR data (uses cache after first run)...")
war_cache    = load_war_cache()
career_cache = load_career_cache()

output_players = []
for pid, pm in player_map.items():
    war_data = get_war_for_player(pid, pm["full_name"], war_cache)
    games_seen = len(pm["game_pks"])
    curated = player_curation.get(pid, {}) or {}

    score = ranking_score(
        career_war=war_data["career_war"],
        peak_war=war_data["peak_war"],
        games_seen=games_seen,
        birth_year=None,
        years_in_mlb=None,
    )

    # Format IP
    ip_raw = pm["pitching"].get("IP", 0)
    ip_whole = int(ip_raw)
    ip_frac = round((ip_raw - ip_whole) * 3)
    ip_display = f"{ip_whole}.{ip_frac}" if ip_frac else str(ip_whole)

    # Classify pitcher role and compute pitcher ranking score
    pitcher_role = None
    pitcher_ranking_score = 0.0
    if "pitcher" in pm["roles"]:
        # curation.yaml can override with pitcher_role: starter/reliever
        curation_role = curated.get("pitcher_role")
        if curation_role in ("starter", "reliever"):
            pitcher_role = curation_role
        else:
            # Use career GS/G ratio from MLB Stats API — same logic as BBRef/JAWS
            pitcher_role = get_pitcher_role(pid, career_cache)

        peak = war_data["peak_war"]
        career = war_data["career_war"]
        if pitcher_role == "starter":
            # Peak WAR × games seen — rewards dominance over longevity
            pitcher_ranking_score = round(peak * games_seen, 2)
        else:
            # Blended: peak + career longevity bonus + multi-game sighting bonus
            # career × 0.1 rewards elite long-career closers (Chapman, Jansen)
            # (games_seen - 1) × 0.3 gives a small bump for repeat sightings
            pitcher_ranking_score = round(
                peak + (career * 0.1) + (games_seen - 1) * 0.3, 2
            )

    # AVG
    ab = pm["batting"].get("AB", 0)
    h = pm["batting"].get("H", 0)
    avg = f"{h/ab:.3f}".lstrip("0") if ab > 0 else ".000"

    # ERA
    er = pm["pitching"].get("ER", 0)
    ip_f = pm["pitching"].get("IP", 0)
    era = f"{er * 9 / ip_f:.2f}" if ip_f > 0 else "—"

    output_players.append({
        "player_id": pid,
        "full_name": pm["full_name"],
        "level": sorted(pm["level"]),
        "games_seen": games_seen,
        "roles": sorted(pm["roles"]),
        "pitcher_role": pitcher_role,
        "career_war": war_data["career_war"],
        "peak_war": war_data["peak_war"],
        "ranking_score": score,
        "pitcher_ranking_score": pitcher_ranking_score,
        # batting
        "AB":     pm["batting"].get("AB", 0),
        "R":      pm["batting"].get("R", 0),
        "H":      pm["batting"].get("H", 0),
        "RBI":    pm["batting"].get("RBI", 0),
        "BB":     pm["batting"].get("BB", 0),
        "SO_bat": pm["batting"].get("SO", 0),
        "HR":     pm["batting"].get("HR", 0),
        "AVG":    avg,
        # pitching
        "IP":     ip_display,
        "H_pit":  int(pm["pitching"].get("H", 0)),
        "R_pit":  int(pm["pitching"].get("R", 0)),
        "ER":     int(pm["pitching"].get("ER", 0)),
        "BB_pit": int(pm["pitching"].get("BB", 0)),
        "SO_pit": int(pm["pitching"].get("SO", 0)),
        "ERA":    era,
        # curation
        "badge":      curated.get("badge", ""),
        "note":       curated.get("note", ""),
        "cross_refs": curated.get("cross_refs", []),
        # MiLB flags
        "milb_only":    pm["level"] == {"MiLB"},
        "seen_in_milb": "MiLB" in pm["level"],
    })

# ── Sort and write ───────────────────────────────────────────────
output_players.sort(key=lambda p: p["ranking_score"], reverse=True)

payload = json.dumps(output_players, indent=2)
out_path = ROOT / "data" / "players.json"
out_path.write_text(payload)

# Keep dashboard copy in sync
dashboard_copy = ROOT / "dashboard" / "players.json"
dashboard_copy.write_text(payload)

print(f"\nDone. {len(output_players)} players written to {out_path}")
print("Top 10 by ranking score:")
for p in output_players[:10]:
    print(f"  {p['full_name']:30}  score={p['ranking_score']:8.1f}  "
          f"WAR={p['career_war']:6.1f}  G={p['games_seen']}")
