# wc26-ko ⚽

A tiny static site for the **2026 FIFA World Cup knockout stage** — side-by-side
team comparison pages for each match, plus a bracket index. 🏆

**Live site:** <https://stvsmth.github.io/wc26-ko/compare/index.html>

## How it works

Everything is generated from a couple of TOML files by a single, stdlib-only
Python script:

- `data/teams.toml` — per-team stats and 26-man squads
- `data/rounds/*.toml` — fixtures for each knockout round

Running the build reads those files and writes one comparison page per match
into `compare/`, plus `compare/index.html`. The script owns `compare/` and
clears it on every run.

## Build 🔨

Requires Python 3.11+ (for `tomllib`). No dependencies to install.

```sh
python3 build.py
```

Then open `index.html` (or `compare/index.html`) in a browser.

## Layout 📁

| Path             | What's there                                  |
| ---------------- | --------------------------------------------- |
| `build.py`       | The static-site generator                     |
| `data/`          | Source TOML (teams + fixtures)                |
| `teams/`         | Per-team HTML profiles                        |
| `compare/`       | Generated match pages (don't hand-edit)       |
| `scripts/`       | Helpers (e.g. `extract_teams.py`)             |
| `assets/`        | CSS + JS                                       |

## License 📄

MIT — see [LICENSE](LICENSE).
