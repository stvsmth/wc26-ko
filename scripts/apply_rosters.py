#!/usr/bin/env python3
"""Apply researched 26-man rosters (data/rosters/<slug>.toml) onto the hand-authored
teams/<slug>.html profile pages.

For each roster file it rewrites ONLY the squad block — from `<div class="squad-head">`
through the closing `</table>` — and refreshes the "Squad avg age" factstrip value /
squad-size label. Everything else on the page (hero, blurb, coach, footer) is left
untouched. Idempotent: re-running with the same data reproduces the same HTML.

After this, re-scaffold + rebuild:
    python3 scripts/apply_rosters.py
    python3 scripts/extract_teams.py
    python3 build.py

Roster file schema (data/rosters/argentina.toml):
    slug = "argentina"
    [[player]]
    num = 23
    name = "Emiliano Martínez"
    pos = "GK"                 # GK | DF | MF | FW
    club = "Aston Villa (ENG)"
    age = 33
    caps = 62
    captain = true            # optional, at most one per squad
"""

import html
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAMS_DIR = ROOT / 'teams'
ROSTERS_DIR = ROOT / 'data' / 'rosters'

SQUAD_BLOCK_RE = re.compile(r'<div class="squad-head">.*?</table>', re.S)
AVG_RE = re.compile(
    r'(<div class="k">Squad avg age</div><div class="v">)\s*[\d.]+\s*'
    r'<small>[^<]*</small>'
)
POS_ORDER = {'GK': 0, 'DF': 1, 'MF': 2, 'FW': 3}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def row_html(p: dict) -> str:
    cap = '<span class="cap">(C)</span>' if p.get('captain') else ''
    return (
        '\n              '
        f'<td class="shirt-cell">{p["num"]}</td>'
        f'<td><span class="pos pos-{p["pos"]}">{p["pos"]}</span></td>'
        f'<td class="pname">{esc(p["name"])}{cap}</td>'
        f'<td class="club">{esc(p["club"])}</td>'
        f'<td class="age-cell">{p["age"]}</td>'
        f'<td class="num-cell">{p["caps"]}</td>'
    )


def squad_block(players: list) -> str:
    rows = '</tr><tr>'.join(row_html(p) for p in players)
    return (
        '<div class="squad-head"><h2>Squad</h2>\n'
        '            <span class="note">Full 26-man squad · '
        'club at selection · senior caps</span></div>\n'
        '          <table class="squad"><thead><tr>\n'
        '            <th>#</th><th>Pos</th><th>Player</th>'
        '<th>Club (league)</th><th>Age</th><th>Caps</th>\n'
        f'          </tr></thead><tbody><tr>{rows}</tr></tbody></table>'
    )


def apply(path: Path) -> str:
    with path.open('rb') as fh:
        data = tomllib.load(fh)
    slug = data.get('slug', path.stem)
    players = data.get('player', [])

    problems = []
    if len(players) != 26:
        problems.append(f'{len(players)} players (expected 26)')
    nums = [p['num'] for p in players]
    if len(set(nums)) != len(nums):
        problems.append('duplicate shirt numbers')
    caps_marked = sum(1 for p in players if p.get('captain'))
    if caps_marked != 1:
        problems.append(f'{caps_marked} captains marked (expected 1)')
    for p in players:
        if p['pos'] not in POS_ORDER:
            problems.append(f'bad pos {p["pos"]!r} for {p["name"]}')

    # Stable display order: GK, DF, MF, FW, then shirt number within group.
    players = sorted(players, key=lambda p: (POS_ORDER.get(p['pos'], 9), p['num']))

    target = TEAMS_DIR / f'{slug}.html'
    if not target.exists():
        sys.exit(f'apply_rosters: {target} not found (roster {path.name})')
    raw = target.read_text(encoding='utf-8')

    if not SQUAD_BLOCK_RE.search(raw):
        sys.exit(f'apply_rosters: no squad block found in {target}')
    raw = SQUAD_BLOCK_RE.sub(lambda _: squad_block(players), raw, count=1)

    n = len(players)
    avg = sum(p['age'] for p in players) / n if n else 0
    raw, hits = AVG_RE.subn(
        lambda m: f'{m.group(1)}{avg:.1f}\n          <small>{n}-player squad</small>',
        raw,
        count=1,
    )
    if not hits:
        problems.append("no 'Squad avg age' factstrip to update")

    target.write_text(raw, encoding='utf-8')
    flag = '  ⚠ ' + '; '.join(problems) if problems else ''
    print(f'  {slug:14} {n} players  avg {avg:.1f}{flag}')
    return slug


def main() -> None:
    if not ROSTERS_DIR.exists():
        sys.exit(f'apply_rosters: {ROSTERS_DIR} not found')
    files = sorted(ROSTERS_DIR.glob('*.toml'))
    if not files:
        sys.exit(f'apply_rosters: no roster files in {ROSTERS_DIR}')
    print(f'Applying {len(files)} roster(s):')
    for f in files:
        apply(f)
    print(f'Done. Now run: python3 scripts/extract_teams.py && python3 build.py')


if __name__ == '__main__':
    main()
