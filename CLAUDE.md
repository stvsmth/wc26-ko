# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository.

## What this is

A static site for the 2026 FIFA World Cup knockout stage: side-by-side match
comparison pages plus a bracket index. Pure stdlib Python generators (3.11+ for
`tomllib`) — no third-party runtime dependencies. Output is committed to the repo
and served via GitHub Pages at `compare/index.html`.

## Commands

```sh
python3 build.py                      # regenerate compare/ from data/ (the build)
python3 scripts/apply_rosters.py      # write rosters into teams/*.html squad blocks
python3 scripts/extract_teams.py      # re-scaffold data/teams.toml from teams/*.html
ruff format <files>                   # format (line-length 99, single quotes; see pyproject.toml)
ruff check <files>                    # lint
ty check                              # type-check (dev dependency; see pyproject.toml)
```

There is no test suite. Validation is built into the generators: they `sys.exit`
with a `<file>: error:` message on bad/missing data rather than producing broken
pages. After a build, open `compare/index.html` in a browser to verify.

## The data flow (the key thing to understand)

The pipeline runs in a specific order because each stage's *output is the next
stage's input*, and `teams/*.html` is both a hand-authored source AND a generated
artifact depending on the stage:

```text
data/rosters/<slug>.toml  ──apply_rosters.py──►  teams/<slug>.html  (squad block rewritten in place)
teams/<slug>.html         ──extract_teams.py──►  data/teams.toml    (stats + squads scaffolded out)
data/teams.toml + data/rounds/*.toml  ──build.py──►  compare/*.html + compare/index.html
```

So the full refresh sequence after editing a roster is:

```sh
python3 scripts/apply_rosters.py && python3 scripts/extract_teams.py && python3 build.py
```

Ownership rules that are easy to get wrong:

- **`build.py` owns `compare/`** — it clears and regenerates every `.html` there
  on each run. Never hand-edit files in `compare/`; edit the generator or the
  source TOML instead.
- **`teams/*.html` is hand-authored**, except the squad block (`<div
  class="squad-head">…</table>`) and the "Squad avg age" factstrip, which
  `apply_rosters.py` rewrites via regex. Hero, blurb, coach, and footer are left
  untouched. The script is idempotent.
- **`data/teams.toml` is a hand-editable artifact.** `extract_teams.py` only
  *scaffolds* it from the HTML; `build.py` never rewrites it. Re-run
  `extract_teams.py` only to re-scaffold, and spot-check the result.
- Team identity is a **slug** (the `teams/<slug>.html` stem), used as the TOML
  table key and referenced by `home`/`away` in round files. Keeping slugs
  consistent across all three layers is what holds the pipeline together.

## build.py specifics

- `FLAG_CODES` maps each team slug → flag-icons code (ISO 3166-1 alpha-2). It must
  contain every team in the bracket; `flag()` calls `die()` on any unmapped slug,
  so the build fails loudly. England uses `gb-eng` (St George's Cross), not `gb`.
- `CONF_VARS_STYLE` is an inline `:root` block emitted into every generated
  `<head>` *before* the external stylesheet, so confederation accent colors are
  defined on first paint (avoids a load-time blue flash). Keep it in sync with
  the `:root` block in `style.css`. The hand-authored `teams/*.html` and root
  `index.html` carry their own copy of this block — if you change the
  confederation palette, update all of: `style.css`, `build.py`'s
  `CONF_VARS_STYLE`, and every page that inlines it.
- Confederation accent colors are driven by inline `style="--accent:var(--conf-<conf>)"`
  attributes plus the `--conf-*` CSS vars; `accent()`/`conf_label()` produce them.
- `times.js` upgrades each `<time class="kickoff">` element to the viewer's local
  zone at runtime; the server-rendered text is the venue-local no-JS fallback.

## Conventions

- Code style is enforced by ruff (`pyproject.toml`): 99-column lines, single
  quotes for regular strings, double quotes preserved for docstrings.
- Stdlib only for anything that runs in the build — do not add runtime
  dependencies. (`ruff`/`ty` are dev-time tooling only.)
- Roster TOML (`data/rosters/<slug>.toml`) expects exactly 26 players, unique
  shirt numbers, exactly one `captain = true`, and `pos` in GK/DF/MF/FW;
  `apply_rosters.py` warns (⚠) on violations rather than failing.
- Roster data is researched and validated against Wikipedia's 2026 FIFA World
  Cup squads (verify each player, shirt number, and the full 26-man list).

## Before committing

- Run `ruff check --fix` (then `ruff format`) to lint and auto-fix.
- Run `ty check` after any large change, and before committing Python changes.
- Run `rumdl fmt` on touched Markdown files (config in `.rumdl.toml`).
- Write commit messages in Tim Pope style: a ~50-char capitalized summary in the
  imperative mood ("Add flag icons", not "Added"/"Adds"), no trailing period. If
  a body is warranted, separate it with a blank line and wrap at 72 columns,
  explaining *what* and *why* rather than *how*. Omit the body entirely for
  obvious/self-explanatory changes — a good summary line is often enough.
