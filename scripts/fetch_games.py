"""
Fetches box scores for all games in games.yaml using the MLB Stats API.
Caches raw responses locally to avoid re-fetching.
"""

import json
import time
import requests
from pathlib import Path

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
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
    time.sleep(0.3)
    return data


def extract_players(pk: int, level: str) -> list[dict]:
    """
    Returns a list of player appearances from a single game box score.
    Each entry: {player_id, full_name, team, level, game_pk, role, stats}
    """
    data = get_boxscore(pk)
    players = []

    for side in ("away", "home"):
        team_data = data["teams"][side]
        team_name = team_data["team"]["name"]

        for p in team_data.get("players", {}).values():
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
