# Roadmap: Make the generator generic for any World Cup edition

## Context

The repo (`wc26-ko`) is a stdlib-Python static-site generator hardwired to the
2026 men's World Cup. The tournament name, year, hosts, ranking date, team count
(32), and squad size (26) are hardcoded across `build.py`, the hand-authored
`teams/*.html` (32 files), and `index.html`. There is no notion of "which
tournament," so a new edition (e.g. the 2027 Women's World Cup) would mean a new
repo and ~40 hand-edited files.

**Goal:** one repo that hosts **many events** (men's or women's, any year),
driven by data. Three decisions are locked in:

1. **One repo, many events** — `data/events/<slug>/`; output to per-event
   subdirs; a root index links to each event.
2. **Generate `teams/*.html` fully from data** — port the hand-authored team-page
   layout into `build.py`; retire HTML round-tripping.
3. **Parameterize metadata + counts only** — name, short name, gender, year,
   hosts, ranking label/date, team count, squad size, round names. The 6
   confederations and GK/DF/MF/FW positions stay global constants in `build.py`.

The work is too large for one change, so it is staged into **five stages, each
with a single concern and each independently shippable and browser-verifiable.**
Every stage ends in a clean `python3 build.py` of the existing event; Stage 4
proves genericity with a second event.

## Stage summary (one concern each)

| Stage | Single concern | Output changes? | Risk |
|---|---|---|---|
| 0 | Config: extract hardcoded strings into `event.toml` | no | low |
| 1 | Data model: rosters single-source, join + derive + validate | no | low |
| 2 | Templating: generate all HTML into final per-event layout | **yes** | high |
| 3 | Multi-event: loop the build + relocate data | no (per event) | med |
| 4 | Validation: add a 2nd (women's) event + docs | adds event | low |

The split is deliberate: Stage 1 (data plumbing) and Stage 2 (templating/layout)
are orthogonal — keeping them apart means each is verified in isolation. Stage 2
emits the **final** layout directly (not a flat layout that Stage 3 then moves),
so Stage 3 changes only *input* paths and adds the loop — zero HTML churn.

## Target architecture

```text
data/
  events/
    wc2026/
      event.toml          # tournament metadata (NEW)
      teams.toml          # per-team metadata + blurb (no players, no derived stats)
      rounds/r32.toml     # fixtures (unchanged shape)
      rosters/<slug>.toml # canonical 26-man squads (one file per team)
  # (wc2027-women/ added in Stage 4)

build.py                  # owns ALL html; loops over events
style.css, assets/        # shared, stay at repo root (GitHub Pages root)

# generated output (build.py owns these trees):
index.html                # root event picker
wc2026/index.html         # team grid for the event
wc2026/teams/<slug>.html  # generated team profiles
wc2026/compare/*.html     # generated comparison pages + index
```

The pipeline becomes **linear** (no more HTML→TOML→HTML round-trip):

```text
event.toml + teams.toml + rounds/*.toml + rosters/*.toml ──build.py──► <slug>/**.html + root index.html
```

---

## Stage 0 — Config layer (de-hardcode strings; output unchanged)

Concern: pull tournament-specific strings out of code into one config file.
Nothing is retired, no paths move, output stays byte-stable except the
now-config-sourced strings.

- Add `data/event.toml` for the current event (temporary flat location; moves to
  `data/events/wc2026/` in Stage 3):

  ```toml
  slug          = "wc2026"
  name          = "FIFA World Cup 2026"
  short_name    = "WC2026"
  gender        = "men"            # "men" | "women"
  year          = 2026
  hosts         = ["Canada", "Mexico", "USA"]
  team_count    = 32
  squad_size    = 26
  ranking_label = "FIFA Rank"
  ranking_date  = "2026-06-11"     # ISO; formatted in build.py
  kicker        = "The Knockout Field"
  headline      = "Round of 32"    # index hero; NOT literal once R16/QF exist
  status_note   = "Group stage complete (Group J settles Jun 28)"
  sources_note  = "Bracket: Wikipedia/ESPN · Squads: official federation announcements"
  ```

- Add a small `EventConfig` loader + a `fmt_date()` helper that renders the ISO
  `ranking_date` into the two display forms in use ("11 Jun 2026" / "11 June 2026").
- Replace hardcoded strings in `build.py` with config lookups:
  - `WC2026` titles — `render_match` (`build.py:260`), `render_index` (`build.py:319`) → `cfg.short_name`.
  - `11 Jun 2026` footer — `build.py:283-284` → `fmt_date(cfg.ranking_date)`.
  - `All 32 teams` back-link — `build.py:328` → `cfg.team_count`.
  - Module docstring (`build.py:2`).

**Ship/verify:** `python3 build.py`; diff `compare/` — identical except the
config-sourced strings. Open `compare/index.html`.

---

## Stage 1 — Data model: rosters single-source, join + derive + validate (output unchanged)

Concern: collapse the triple-handling of squad data (rosters/*.toml ↔ duplicated
`players` in teams.toml ↔ `apply_rosters.py` HTML injection) into one source,
with derivation and validation living in the build. **No template or layout
change** — compare pages read the same joined team dict, so output is unaffected.

- `data/rosters/<slug>.toml` (`[[player]]`) becomes the **canonical** squad.
  Strip `players`, `avg_age`, `squad_size` out of `teams.toml`.
- `load_teams()` joins each team's metadata with its roster and **derives**
  `avg_age = mean(ages)` and `squad_size = len(players)` (kills the stored-derived
  drift). `render_match`/`squad_html` already read `players`/`avg_age`/`squad_size`
  off the team dict (`build.py:199, 254-255`) — unchanged once the join populates them.
- Add a per-team `flag = "ar"` field to `teams.toml` and have `flag()` prefer it,
  falling back to `FLAG_CODES` (England = `gb-eng`). Add a startup check that every
  team resolves a flag — this turns the soft FLAG_CODES dependency into an explicit,
  data-owned one before Stage 2 makes it hard.
- **Port `apply_rosters.py`'s validation into the loader**: exactly `cfg.squad_size`
  players, unique shirt numbers, exactly one `captain = true`, `pos ∈ GK/DF/MF/FW`.
  Don't lose it.
- Retire `scripts/apply_rosters.py` and `scripts/extract_teams.py` (teams.toml is
  now the hand-maintained source; no more HTML round-trip). The hand-authored
  `teams/*.html` stay in place, frozen, until Stage 2 regenerates them.

**Ship/verify:** `python3 build.py`; `compare/` output identical to Stage 0.
Confirm the loader rejects a deliberately broken roster (drop a player) with a
`build.py: error:` exit.

---

## Stage 2 — Templating: generate ALL html into the final per-event layout (output changes; highest risk)

Concern: `build.py` takes ownership of every page and emits the **final**
`<slug>/` layout. This is the heavy stage; do generation and output-relocation
together because they are physically coupled (you can't move hand-authored pages
into subdirs without generating them).

### 2a. Link-resolution helper (first)

Add a helper that computes every href as `os.path.relpath(target, page_dir)` from
a page's output path to the shared root, so **no `../` depth lives in template
strings**. Depth map (shared `style.css`/`assets/` stay at repo root):

| Page | output | style.css |
|---|---|---|
| root picker | `index.html` | `style.css` |
| event grid | `<slug>/index.html` | `../style.css` |
| team profile | `<slug>/teams/x.html` | `../../style.css` |
| compare page | `<slug>/compare/x.html` | `../../style.css` |

(The flag-icons CDN `@import` in `style.css` is an absolute URL — depth-independent, leave it.)

### 2b. Audit prose before porting (fidelity gate)

`extract_teams.py` never captured some hand-authored prose. **Before** deleting the
reference `teams/*.html`, audit one page field-by-field against `teams.toml` and add
the missing fields, or accept (and document) fidelity loss. Known gaps:
- `group_result` caption (the `<small>` "R32: vs Group H runner-up").
- "Next fixture" caption ("Won 2022 World Cup & 2021/2024 Copa América").
- The next-fixture **link/opponent** is currently hand-typed — derive it from `rounds/`.

### 2c. Port templates into `build.py`

- `render_team()` — hero, flag, accent bar, conf label (drop hardcoded "World Cup
  2026" → `cfg.name`), blurb, factstrip (coach, group result, derived squad avg
  age, next fixture derived from `rounds/`), squad table, footer. Reuse
  `CONF_VARS_STYLE`, `accent()`, `conf_label()`, `flag()`, `squad_html` patterns.
  Drop the stored `profile` path (`squad_html` `build.py:219-220`); derive the
  profile href from slug via the relpath helper.
- `render_event_index()` — port `index.html` (team grid; per-card opponent is a
  join against `rounds/`; hero text from `cfg`).
- `render_root_index()` — new minimal root event picker (one card per event;
  single event for now).
- Emit `index.html`, `wc2026/index.html`, `wc2026/teams/*.html`, `wc2026/compare/*.html`.
- **Scope the output-clear precisely** to the per-event tree (replaces the
  `OUT_DIR.glob('*.html')` clear at `build.py:354-356`) — it must NOT sit above
  `style.css`/`assets/`/root `index.html`.
- Delete the now-regenerated hand-authored `teams/*.html` and `index.html`.

**Ship/verify:** `python3 build.py`; open `index.html` → event → a team profile →
a compare page. Check flags, accent colors, all nav, next-fixture links. Note the
live URL changes (`/compare/...` → `/wc2026/...`) — README/bookmarks update in
Stage 4.

---

## Stage 3 — Multi-event: loop the build + relocate data (no HTML churn)

Concern: input-side only. Output layout and link resolution are already final, so
this stage adds zero HTML churn — it changes where data is read and wraps the
build in a loop.

- Move `data/event.toml`, `data/teams.toml`, `data/rounds/`, `data/rosters/` into
  `data/events/wc2026/`.
- Loader iterates `data/events/*/` (each dir = one event; `slug` defaults to the
  dir name). Per-event paths replace module-level `TEAMS_FILE`/`ROUNDS_DIR`.
- Wrap `main()` in a per-event loop; each event renders its own `<slug>/` tree.
- `render_root_index()` lists all discovered events.

**Ship/verify:** `python3 build.py` reproduces the identical `wc2026/` tree from
the relocated data; root `index.html` lists the one event.

---

## Stage 4 — Validate genericity with a second event + docs

Concern: prove a new edition is **data only**, then update docs.

- Scaffold `data/events/wc2027-women/` (`event.toml` with `gender = "women"`, a few
  teams + one round + rosters). Squad size / team count flow from `event.toml`;
  no code or hand-HTML required.
- Rewrite `README.md` and `CLAUDE.md`: the now-linear data flow (no extract/apply
  round-trip), `data/events/<slug>/` layout, per-event output dirs, retired
  scripts, new commands. (CLAUDE.md's "data flow" and "ownership" sections are now
  stale.)

**Ship/verify:** build produces both event trees; root picker links both; the
women's event renders with its own counts.

---

## Risks & gotchas

1. **`render_team` silently dropping prose** (highest risk) — gated by the 2b audit.
2. **Losing roster validation** when `apply_rosters.py` retires — ported into the
   loader in Stage 1.
3. **FLAG_CODES soft→hard.** It already lists all 32 slugs (not a current bug), but
   today only compare/index pages use it; once team pages generate, a missing slug
   aborts the whole build (`flag()` → `die()`, `build.py:107`). Mitigated by moving
   `flag` into team data + a startup check in Stage 1.
4. **Over-broad output-clear** nuking shared `style.css`/`assets/`/root index —
   scope the clear to `<slug>/` (Stage 2c).
5. **Derived-value drift** — compute `avg_age`/`squad_size`, don't store them (Stage 1).
6. **`headline` can't stay "Round of 32"** once R16/QF exist — it's in `event.toml`.
7. **GitHub Pages** — root `index.html` is now generated; ensure the clear never
   deletes it; no Jekyll `_`-dirs are introduced.

## Critical files

- `build.py` — config loader + `fmt_date` (S0); roster join, derivation, validation,
  `flag` field (S1); relpath helper, `render_team`/`render_event_index`/
  `render_root_index`, scoped clear (S2); per-event loop (S3).
- `scripts/apply_rosters.py` (validation to salvage), `scripts/extract_teams.py`
  (retire) — both S1.
- `teams/argentina.html`, `index.html` — layout reference to port, then delete (S2).
- `data/teams.toml`, `data/rounds/r32.toml`, `data/rosters/*.toml` — reshaped (S1),
  relocated (S3).
- `data/events/<slug>/event.toml` — new config (S0, relocated S3).
- `README.md`, `CLAUDE.md` — docs (S4).

## End-to-end verification

After each stage: `python3 build.py` with no `error:` exit, then open the
generated pages in a browser. Stages 0 and 1 must leave `compare/` output
byte-identical (diff it). Stage 2: click root → event → team → compare and
confirm flags, accent colors, and every link resolve; verify a broken roster
still fails the build. Run `ruff check --fix`, `ruff format`, and `ty check`
before committing each stage; `rumdl fmt` on touched Markdown.
