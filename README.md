# baseball_keeper

A personal dashboard tracking every MLB and MiLB game I've attended, with player stats pulled live from the MLB Stats API and career WAR from Baseball Reference.

## What it does

The build pipeline fetches box scores for every game in `config/games.yaml`, aggregates each player's in-game stats, looks up their career WAR, and produces a ranked `players.json` that powers a local dashboard. The dashboard splits players into three tabs — Batters, Starters, and Relievers — each sorted by a custom ranking formula.

## Project structure

```
config/
  games.yaml        # All attended games (MLB + MiLB) by game PK
  curation.yaml     # Hand-curated badges and notes keyed by MLB player ID

scripts/
  build.py          # Master build script — run this to regenerate players.json
  fetch_games.py    # Fetches and caches box scores from the MLB Stats API
  fetch_war.py      # Downloads career/peak WAR from Baseball Reference via pybaseball
  rank.py           # Ranking score formula for batters

dashboard/
  index.html        # The dashboard (open via local HTTP server)
  players.json      # Generated — do not edit by hand

data/
  players.json      # Same as dashboard/players.json
  cache/            # Cached API responses (box scores, WAR tables, career stats)
```

## Running it

**Install dependencies:**
```bash
pip install pyyaml pybaseball requests
```

**Rebuild the data:**
```bash
python3 scripts/build.py
```

Box scores and WAR data are cached in `data/cache/` so subsequent runs are fast. Delete the cache files to force a full refresh.

**View the dashboard:**
```bash
python3 -m http.server 8787 --directory dashboard
```
Then open `http://localhost:8787` in a browser. The dashboard uses `fetch()` to load `players.json`, so it needs to be served over HTTP rather than opened as a local file.

## Ranking formulas

**Batters:** `career_WAR × games_seen`

**Starters:** `peak_WAR (3-year) × games_seen`

**Relievers:** `peak_WAR + (career_WAR × 0.1) + (games_seen − 1) × 0.3`

Peak WAR is the sum of a player's three best individual seasons (JAWS-inspired). The reliever formula blends peak quality with a small career longevity bonus, since relievers inherently accumulate less WAR than starters.

Starter vs. reliever classification uses each player's career GS/G ratio from the MLB Stats API (GS/G > 0.5 = starter), with manual overrides available in `curation.yaml` via `pitcher_role: starter/reliever`.

## Adding a game

Add the game's MLB Stats API PK to `config/games.yaml` under `mlb:` or `milb:`, then run `build.py`. The PK can be found via:

```
https://statsapi.mlb.com/api/v1/schedule?sportId=1&date=YYYY-MM-DD   # MLB
https://statsapi.mlb.com/api/v1/schedule?sportId=11&date=YYYY-MM-DD  # AAA
```

## Curating players

`config/curation.yaml` is never overwritten by the build script. Add entries keyed by MLB player ID to attach a badge and note that appear in the dashboard tooltip.

```yaml
660271:  # Shohei Ohtani
  badge: "🌟"
  note: "2021 & 2023 AL MVP (both unanimous); 2024 NL MVP; 50-50 season"
```

Available badges: `🏛️` HOF · `🌟` Future HOF/superstar · `⭐` Notable star · `🏆` Award/milestone · `🔄` Multi-team · `🌱` Prospect · `📖` Story

To override a pitcher's role: add `pitcher_role: starter` or `pitcher_role: reliever` to their entry.
