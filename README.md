# baseball_keeper

A personal dashboard tracking every MLB and MiLB game I've attended, with player stats pulled live from the MLB Stats API and career WAR from Baseball Reference.

## What it does

The build pipeline fetches box scores for every game in `config/games.yaml`, aggregates each player's in-game stats, looks up their career WAR, and produces ranked JSON files that power a local dashboard. The dashboard has six tabs:

- **Home** — summary stat cards, top-5 ranked lists for batters/starters/relievers, and the most recent games
- **Batters / Starters / Relievers** — ranked player tables with sortable stats and badge tooltips
- **Games** — a card for every attended game with score, decisions, top performer, and hand-written narrative; click any card to expand the full inning-by-inning linescore and box score
- **Parks & Teams** — MLB coverage wall showing all 30 teams organized by division; stadium chip is filled if you've attended a game there, outline if not

## Project structure

```
config/
  games.yaml        # All attended games (MLB + MiLB) by game PK
  curation.yaml     # Hand-curated badges and notes keyed by MLB player ID
  game_notes.yaml   # Hand-written narrative descriptions for each game card

scripts/
  build.py          # Master build script — run this to regenerate all JSON
  fetch_games.py    # Fetches and caches box scores from the MLB Stats API
  fetch_game_cards.py  # Fetches score, WP/LP, top performer, linescore, and box score lines
  fetch_war.py      # Downloads career/peak WAR from Baseball Reference via pybaseball
  rank.py           # Ranking score formula for batters

dashboard/
  index.html        # The dashboard (open via local HTTP server)
  players.json      # Generated — do not edit by hand
  games.json        # Generated — do not edit by hand

data/
  players.json      # Same as dashboard/players.json
  games.json        # Same as dashboard/games.json
  cache/            # Cached API responses (box scores, game cards, WAR tables)
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

## Game cards

Each game in the Games tab shows:

- **Score** — final score with the winning team highlighted
- **WP / LP / SV** — pitcher decisions pulled automatically from the MLB Stats API
- **Top performer** — the highest-scoring hitter from the winning team (by API game score), with their stat line
- **Note** — a hand-written description from `config/game_notes.yaml`

Click a card header to expand the full box score:

- **Linescore** — runs by inning for both teams, plus R/H/E totals
- **Batting lines** — full lineup with AB/R/H/RBI/HR/BB/SO; pinch hitters and defensive replacements are indented below their batting order slot
- **Pitching lines** — IP/H/ER/BB/SO with win/loss/save notation

The Games tab also has **Expand all** and **Collapse all** buttons to open or close every card at once.

The `game_notes.yaml` file is never overwritten by the build script. Add or edit a note for any game:

```yaml
490629:  # May 12 2017 · HOU @ NYY
  note: >
    An ALCS preview in May. These two teams would meet in the ALCS three times
    over the next six years, with Houston winning each time.
```

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
