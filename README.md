# baseball_keeper

A personal dashboard tracking every MLB and MiLB game I've attended, with player stats pulled live from the MLB Stats API, career WAR from Baseball Reference, and Statcast data from Baseball Savant.

## What it does

The build pipeline fetches box scores for every game in `config/games.yaml`, aggregates each player's in-game stats, looks up their career WAR, and produces ranked JSON files that power a local dashboard. A separate Statcast script fetches pitch-by-pitch data from Baseball Savant for each MLB game. The dashboard has seven tabs:

- **Home** — summary stat cards, a Spotify Wrapped-style superlatives carousel (farthest HR seen, fastest pitch, rarest feat, most-seen player, and more), top-5 ranked lists for batters/starters/relievers, and the most recent games
- **Batters / Starters / Relievers** — ranked player tables with sortable stats and badge tooltips
- **Games** — a card for every attended game with score, decisions, top performer, and hand-written narrative; click any card to expand the full inning-by-inning linescore and box score
- **Parks & Teams** — MLB coverage wall showing all 30 teams organized by division; stadium chip is filled if you've attended a game there, outline if not; MiLB teams are tucked under their parent club
- **⚡ Statcast** — top-10 leaderboards across all MLB games attended for five categories: farthest home run, hardest exit velocity, fastest pitch, highest spin rate, and most pitch movement; click any row for a detail modal with full game situation, pitch location SVG, and a 🎥 Watch link to the Baseball Savant video

## Project structure

```
config/
  games.yaml        # All attended games (MLB + MiLB) by game PK
  curation.yaml     # Hand-curated badges and notes keyed by MLB player ID
  game_notes.yaml   # Hand-written narrative descriptions for each game card

scripts/
  build.py             # Master build script — run this to regenerate all JSON
  fetch_games.py       # Fetches and caches box scores from the MLB Stats API
  fetch_game_cards.py  # Fetches score, WP/LP, top performer, linescore, and box score lines
  fetch_war.py         # Downloads career/peak WAR from Baseball Reference via pybaseball
  fetch_statcast.py    # Downloads Statcast CSVs from Baseball Savant and builds top-10 JSON
  rank.py              # Ranking score formula for batters

dashboard/
  index.html                   # The dashboard (open via local HTTP server)
  players.json                 # Generated — do not edit by hand
  games.json                   # Generated — do not edit by hand
  statcast_superlatives.json   # Generated — do not edit by hand

data/
  players.json      # Same as dashboard/players.json
  games.json        # Same as dashboard/games.json
  statcast_superlatives.json   # Same as dashboard/statcast_superlatives.json
  cache/            # Cached API responses (box scores, game cards, WAR tables)
  cache/statcast/   # Cached Statcast CSVs (one per game PK)
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

**Rebuild Statcast data** (MLB games only):
```bash
python3 scripts/fetch_statcast.py
```

Box scores, WAR data, and Statcast CSVs are all cached in `data/cache/` so subsequent runs are fast. Delete the relevant cache files to force a full refresh.

**View the dashboard:**
```bash
python3 -m http.server 8787 --directory dashboard
```
Then open `http://localhost:8787` in a browser. The dashboard uses `fetch()` to load JSON, so it needs to be served over HTTP rather than opened as a local file.

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

## Statcast tab

`fetch_statcast.py` downloads a pitch-by-pitch CSV from Baseball Savant for each MLB game and builds five top-10 leaderboards:

| Category | Stat field |
|---|---|
| Farthest home run | `hit_distance_sc` (ft) |
| Hardest exit velocity | `launch_speed` (mph) |
| Fastest pitch | `release_speed` (mph) |
| Highest spin rate | `release_spin_rate` (RPM) |
| Most pitch movement | vector of `api_break_x_batter_in` + `api_break_z_with_gravity` (in) |

Each event in the detail modal shows:
- **Game situation** — inning/half, outs, count, runners on base (diamond graphic)
- **Score** at the time of the pitch
- **Opposing player** — pitcher for batted-ball events, batter for pitch events
- **Result** — pitch description and play narrative from the `des` field
- **Pitch location SVG** — rendered using real `plate_x`/`plate_z` coordinates and the batter's actual strike zone bounds (`sz_top`/`sz_bot`); red dot = in zone
- **🎥 Watch** — links to the Baseball Savant video, defaulting to the player's own broadcast feed (AWAY for away-team players, HOME for home-team players)

CSVs are cached in `data/cache/statcast/` after the first fetch. Play IDs for the video links are matched from the cached gamecard JSONs using `at_bat_number` + `pitch_number`.

## Adding a game

Add the game's MLB Stats API PK to `config/games.yaml` under `mlb:` or `milb:`, then run `build.py`. For Statcast data on the new game, also run `fetch_statcast.py`. The PK can be found via:

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

---

## Roadmap

Planned improvements in rough priority order. Nothing here is started yet.

---

### Backend / Pipeline

#### B1 — Parallel API fetching
`fetch_all_appearances()` and `fetch_all_game_cards()` both iterate through games sequentially. On a cold run (empty cache, new machine) every HTTP request blocks the next one. The fix is `concurrent.futures.ThreadPoolExecutor` — each game fetches in its own worker thread, the cache-hit check stays inside each worker so already-cached games are still instant. The existing `time.sleep()` rate-limit delay would only apply in the non-cached path. On a full cold run this cuts fetch time from roughly `O(n × 0.3s)` to `O(n/6 × 0.3s)`.

#### B2 — Smarter WAR cache write strategy
Two problems in `fetch_war.py`: (1) `save_war_cache()` is called inside the per-player loop, so a build with 300 players does 300 separate file writes to `war_data.json`. Fix: accumulate in memory, write once at the end of `build.py`. (2) The full BBRef WAR tables (`bwar_bat`, `bwar_pitch`) are re-downloaded from pybaseball on every single build run — they only update a few times a season. Fix: serialize the DataFrames to `data/cache/bwar_bat.pkl` / `bwar_pitch.pkl` with a 7-day file-age TTL. On a non-stale run the pickle loads in milliseconds instead of hitting BBRef.

#### B3 — Incremental builds
Every `python build.py` currently re-parses every player and every game from scratch even though the underlying cache files haven't changed. Fix: write a `data/build_manifest.json` after each successful run recording `{pk: {built_at, hash}}` per game. On the next run, skip any game whose PK is in the manifest and whose cache file hash matches. Add a `--full` flag to force a complete rebuild. At the current scale this is a nice-to-have; at 50+ games it becomes genuinely useful.

#### B4 — CLI add-game helper
A single lightweight script (`scripts/add_game.py`) that accepts a game PK as an argument:
```bash
python scripts/add_game.py 822824
```
It hits the MLB schedule API with the PK to retrieve teams and date, auto-detects MLB vs MiLB from the `sportId` in the response, appends the formatted entry (with the `# Apr 26 2026  CLE @ TOR` comment) to `games.yaml`, and optionally triggers `build.py` via a `--build` flag. No new dependencies — uses only `requests`, `pyyaml`, and stdlib `argparse`, all already in the project. Roughly 50–60 lines total.

#### B5 — Integrate Statcast into build
Currently two separate commands are required: `python build.py` then `python fetch_statcast.py`. Statcast is now core enough to be part of the standard pipeline. The plan: add an optional `--with-statcast` flag to `build.py` (or auto-run Statcast for any newly-processed MLB games). `fetch_statcast.py` currently reads `dashboard/games.json` to find MLB game PKs — change it to accept the game list as a parameter so there's no circular file dependency.

#### B5 — Output file strategy
Every generated JSON is written twice: once to `data/` (source of truth) and once to `dashboard/` (served by the HTTP server). This dual-write works but risks the two copies drifting out of sync. Two improvements: (1) **minify** the dashboard copies — `json.dumps(payload)` without `indent=2` cuts file size ~35%, which matters as `players.json` grows; (2) optionally replace the `dashboard/` copies with symlinks to `data/` so there's only ever one file.

#### B6 — Retry logic and error hardening
A transient 429 or 503 from the MLB Stats API or Baseball Savant currently causes a game to be silently skipped — the error is printed but easy to miss. Fix: a shared `fetch_with_retry(url, retries=3, backoff=2.0)` helper used across all fetch scripts, with exponential backoff on 429/5xx and immediate re-raise on 4xx client errors. Add a final build summary that clearly flags any games that failed: `⚠ 2 games could not be fetched: [490629, 746125]`.

---

### Frontend

#### F1 — Animated expand/collapse
Game cards and Statcast sections currently snap open and closed using `display: none / block`, which can't be animated. The fix is the CSS grid row trick — no JavaScript required:
```css
.game-expand {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows .28s ease;
}
.game-expand.open { grid-template-rows: 1fr; }
.game-expand > .expand-inner { overflow: hidden; min-height: 0; }
```
The inline `style="display:none"` attributes on each card get removed; the JS toggles an `.open` class instead of `style.display`. The same pattern applies to Statcast `.sc-body` sections. One commit covers both.

#### F2 — Mobile responsiveness
Several things break on small screens: the tab nav wraps onto a second line (collides with the active-underline design); all section padding is a hardcoded `28px 32px` which consumes ~20% of a 375px viewport; game card grid `minmax(310px, 1fr)` forces single-column layout later than ideal. Fixes: a `@media (max-width: 600px)` block dropping padding to `16px` everywhere; `flex-wrap: nowrap; overflow-x: auto` on the nav so tabs scroll horizontally; game card grid changed to `minmax(260px, 1fr)`; a CSS gradient shadow on the right edge of table scroll containers to indicate there's more content (no JS needed).

#### F3 — Keyboard and focus
Three gaps: (1) no custom `:focus-visible` styles, so keyboard users get inconsistent browser-default outlines — fix with one global rule using `var(--dirt)`; (2) the Statcast detail modal has no Escape key handler — `document.addEventListener('keydown', e => e.key === 'Escape' && closeScModal())` is the entire fix; (3) the modal has no focus trap — on open, focus should move to the close button and Tab should cycle only within `.sc-modal`, restoring focus to the source row on close. Add `aria-expanded` to collapsible headers throughout.

#### F4 — Skeleton loading states
Every tab currently shows plain `Loading…` text until its `fetch()` resolves. Skeleton screens — shaped grey placeholder blocks that match the real content's layout — look dramatically more professional and feel faster even though load time is identical. One `@keyframes shimmer` animation (a gradient sweep) and one `.skel` utility class handles everything. Per-tab skeletons: player tables get 8 placeholder rows; the Home tab gets stat card outlines and carousel placeholders; the Games tab gets 4 skeleton cards; Statcast gets 5 collapsed section headers. All are replaced by the same `innerHTML =` assignment that already runs when data loads — no structural JS changes required.

#### F5 — Carousel position indicator
The superlatives carousel has no indication of position — the only way to know you've reached the last card is that the `›` button stops responding (and it doesn't actually disable, it just doesn't scroll further). Fix: a row of dots below the track, one per card, with the active dot filled in `var(--dirt)`. `carouselScroll()` updates the active dot after each click. A `scroll` event listener on `#carTrack` syncs the dots when the user swipes or drags instead of clicking the buttons. The `‹` and `›` buttons get properly disabled at the start and end respectively.

#### F6 — Type scale consolidation
The CSS currently has approximately 15 distinct font sizes between `.54rem` and `.85rem` — nearly every component uses a slightly different value. Define five size variables in `:root` (`--text-xs` through `--text-lg`) and sweep the CSS replacing every one-off value with the nearest variable. No visual change at all — purely a maintainability improvement that makes future edits more consistent.

#### F7 — Minor polish pass
Small scattered improvements: highlight the entire active sort column (not just the header) with a faint background tint in `renderTable()`; replace the tooltip's `display: none / block` snap with an `opacity` + `transition` fade; add a `transform: translateY(8px) → 0` entrance animation to the Statcast detail modal when it opens; add `transition: opacity .2s` to carousel buttons so the disabled state fades instead of snapping.

#### F8 — Player detail modal
Click any row in the Batters, Starters, or Relievers tabs to open a modal showing that player's full history across all attended games. All the required data already exists: `players.json` includes a `game_pks` array per player, and `games.json` has complete box scores with individual stat lines. The modal would cross-reference these at render time to show a game-by-game breakdown:

```
Bobby Witt Jr.                career WAR 12.4 · peak WAR 7.1
──────────────────────────────────────────────────────────────
KC @ NYY  · Sep 14 2024    2-4   1 HR   2 RBI   1 BB
KC @ HOU  · Jul 04 2024    1-3   0 HR   0 RBI   1 SO
```

For pitchers the lines would show IP/H/ER/BB/SO per appearance. The modal would also surface their curated badge and note if one exists. No new data fetching or build changes required — it's purely a frontend rendering problem.
