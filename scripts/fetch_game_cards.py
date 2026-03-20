"""
Fetches game-level metadata for each game PK:
  - Date, teams, venue, final score
  - Winning/losing pitcher (from decisions)
  - Top hitter on the winning team (from topPerformers)

Uses the MLB Stats API live feed endpoint, which covers both MLB and MiLB.
Caches one JSON file per game PK in data/cache/.
"""

import json
import time
import requests
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
BASE = "https://statsapi.mlb.com/api/v1.1"


def get_game_card_raw(pk: int) -> dict:
    cache_file = CACHE_DIR / f"gamecard_{pk}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    url = f"{BASE}/game/{pk}/feed/live"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    cache_file.write_text(json.dumps(data, indent=2))
    time.sleep(0.3)
    return data


def extract_game_card(pk: int, level: str, note: str = "") -> dict:
    """
    Returns a structured dict for one game card.
    """
    data = get_game_card_raw(pk)
    gd = data["gameData"]
    ld = data["liveData"]

    date_str = gd.get("datetime", {}).get("officialDate", "")
    away_team = gd["teams"]["away"]["name"]
    home_team = gd["teams"]["home"]["name"]
    away_abbr = gd["teams"]["away"].get("abbreviation", away_team[:3].upper())
    home_abbr = gd["teams"]["home"].get("abbreviation", home_team[:3].upper())
    venue = gd.get("venue", {}).get("name", "")

    linescore = ld.get("linescore", {})
    away_score = linescore.get("teams", {}).get("away", {}).get("runs")
    home_score = linescore.get("teams", {}).get("home", {}).get("runs")

    # Fall back to boxscore teamStats if linescore missing
    if away_score is None:
        bs = ld.get("boxscore", {}).get("teams", {})
        away_score = bs.get("away", {}).get("teamStats", {}).get("batting", {}).get("runs", 0)
        home_score = bs.get("home", {}).get("teamStats", {}).get("batting", {}).get("runs", 0)

    decisions = ld.get("decisions", {})
    winning_pitcher = decisions.get("winner", {}).get("fullName", "")
    losing_pitcher  = decisions.get("loser",  {}).get("fullName", "")
    save_pitcher    = decisions.get("save",   {}).get("fullName", "")

    # Winner/loser team
    is_away_winner = linescore.get("teams", {}).get("away", {}).get("isWinner", False)
    winner_abbr = away_abbr if is_away_winner else home_abbr

    # Top hitter from topPerformers — prefer a hitter on the winning team
    top_hitter_name    = ""
    top_hitter_summary = ""
    top_hitter_team    = ""
    bs = ld.get("boxscore", {})
    for perf in bs.get("topPerformers", []):
        if perf.get("type") != "hitter":
            continue
        p = perf["player"]
        summary = p.get("stats", {}).get("batting", {}).get("summary", "")
        if not summary:
            continue
        # Check which team the hitter is on
        parent_team_id = p.get("parentTeamId")
        home_team_id   = gd["teams"]["home"].get("id")
        hitter_abbr    = home_abbr if parent_team_id == home_team_id else away_abbr
        top_hitter_name    = p["person"]["fullName"]
        top_hitter_summary = summary
        top_hitter_team    = hitter_abbr
        # Prefer a winner's hitter but take first available
        if hitter_abbr == winner_abbr:
            break

    return {
        "pk":               pk,
        "level":            level,
        "date":             date_str,
        "away_team":        away_team,
        "away_abbr":        away_abbr,
        "home_team":        home_team,
        "home_abbr":        home_abbr,
        "venue":            venue,
        "away_score":       away_score,
        "home_score":       home_score,
        "winning_pitcher":  winning_pitcher,
        "losing_pitcher":   losing_pitcher,
        "save_pitcher":     save_pitcher,
        "top_hitter":       top_hitter_name,
        "top_hitter_line":  top_hitter_summary,
        "top_hitter_team":  top_hitter_team,
        "note":             note,
    }


def fetch_all_game_cards(games_config: dict, game_notes: dict) -> list[dict]:
    cards = []
    for entry in games_config.get("mlb", []):
        pk = entry["pk"]
        print(f"  Fetching MLB game card {pk}...")
        try:
            cards.append(extract_game_card(pk, "MLB", game_notes.get(pk, "")))
        except Exception as e:
            print(f"    ERROR: {e}")

    for entry in games_config.get("milb", []):
        pk = entry["pk"]
        print(f"  Fetching MiLB game card {pk}...")
        try:
            cards.append(extract_game_card(pk, "MiLB", game_notes.get(pk, "")))
        except Exception as e:
            print(f"    ERROR: {e}")

    cards.sort(key=lambda c: c["date"])
    return cards
