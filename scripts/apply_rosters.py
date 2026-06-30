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
    value = 28000000          # optional, est. Transfermarkt market value in EUR
    captain = true            # optional, at most one per squad
"""

import html
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
TEAMS_DIR = ROOT / 'teams'
ROSTERS_DIR = ROOT / 'data' / 'rosters'

SQUAD_BLOCK_RE = re.compile(r'<div class="squad-head">.*?</table>', re.S)
# The factstrip key/value wrapper that the avg-age substitution rebuilds (via
# m.group(1) below). Exposed as a constant so tests can assert against the real
# markup instead of duplicating it. The prefix has no regex metacharacters.
AVG_PREFIX = '<div class="k">Squad avg age</div><div class="v">'
AVG_RE = re.compile(rf'({AVG_PREFIX})\s*[\d.]+\s*<small>[^<]*</small>')
# The complete avg-age fact (after AVG_RE has refreshed it) — used as the anchor
# to splice the squad-value fact in right after it.
AVG_FACT_FULL_RE = re.compile(
    r'(<div class="k">Squad avg age</div><div class="v">\s*[\d.]+\s*'
    r'<small>[^<]*</small></div></div>)'
)
# The squad-value fact this script inserts; removed first each run so re-applying
# is idempotent rather than stacking duplicates.
VALUE_FACT_KEY = 'Squad market value'
VALUE_FACT_RE = re.compile(
    rf'\s*<div class="fact"><div class="k">{VALUE_FACT_KEY}</div>.*?</div></div>', re.S
)
POS_ORDER = {'GK': 0, 'DF': 1, 'MF': 2, 'FW': 3}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt_value(v: int) -> str:
    """Compact market-value label, e.g. €1.40bn / €180m / €12.5m / €450k."""
    if v >= 1_000_000_000:
        return f'€{v / 1_000_000_000:.2f}bn'
    if v >= 1_000_000:
        m = v / 1_000_000
        return f'€{m:.0f}m' if m >= 100 or m == int(m) else f'€{m:.1f}m'
    if v >= 1_000:
        return f'€{round(v / 1_000)}k'
    return f'€{v}'


def value_fact_html(total: int) -> str:
    """The 'Squad market value' factstrip block spliced after the avg-age fact."""
    return (
        f'\n        <div class="fact"><div class="k">{VALUE_FACT_KEY}</div>'
        f'<div class="v">{fmt_value(total)}\n'
        f'          <small>est.</small></div></div>'
    )


def row_html(p: dict[str, Any]) -> str:
    cap = '<span class="cap">(C)</span>' if p.get('captain') else ''
    v = p.get('value')
    value_td = (
        f'<td class="value-cell" data-eur="{v}">{fmt_value(v)}</td>'
        if v
        else '<td class="value-cell nodata">—</td>'
    )
    return (
        '\n              '
        f'<td class="shirt-cell">{p["num"]}</td>'
        f'<td><span class="pos pos-{p["pos"]}">{p["pos"]}</span></td>'
        f'<td class="pname" data-sort="{esc(p["name"].lower())}">{esc(p["name"])}{cap}</td>'
        f'<td class="club">{esc(p["club"])}</td>'
        f'<td class="age-cell">{p["age"]}</td>'
        f'<td class="num-cell">{p["caps"]}</td>'
        f'{value_td}'
    )


def squad_block(players: list[dict[str, Any]]) -> str:
    rows = '</tr><tr>'.join(row_html(p) for p in players)
    return (
        '<div class="squad-head"><h2>Squad</h2>\n'
        '            <span class="note">Full 26-man squad · '
        'club at selection · senior caps</span></div>\n'
        '          <table class="squad sortable"><thead><tr>\n'
        '            <th data-sort-type="num" aria-sort="ascending">#</th>'
        '<th data-sort-type="pos">Pos</th>'
        '<th data-sort-type="text">Player</th>'
        '<th data-sort-type="text">Club (league)</th>'
        '<th data-sort-type="num">Age</th>'
        '<th data-sort-type="num">Caps</th>'
        '<th data-sort-type="num">Value</th>\n'
        f'          </tr></thead><tbody><tr>{rows}</tr></tbody></table>'
    )


def apply(path: Path) -> str:
    with path.open('rb') as fh:
        data: dict[str, Any] = tomllib.load(fh)
    slug = data.get('slug', path.stem)
    players: list[dict[str, Any]] = data.get('player', [])

    problems: list[str] = []
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

    # Default display order is shirt number; the # header carries
    # aria-sort="ascending" to match, and sort.js reorders on header click.
    players = sorted(players, key=lambda p: p['num'])

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

    # Squad market value: remove any prior fact (idempotency), then splice a
    # fresh one after the avg-age fact when we have at least one valued player.
    raw = VALUE_FACT_RE.sub('', raw)
    vals = [p['value'] for p in players if p.get('value')]
    if vals:
        fact = value_fact_html(sum(vals))
        raw, vhits = AVG_FACT_FULL_RE.subn(lambda m: m.group(1) + fact, raw, count=1)
        if not vhits:
            problems.append('could not anchor squad-value factstrip')

    # Load the column-sort enhancement. Team pages are otherwise script-free, so
    # splice the tag in before </body> once (idempotent across re-runs).
    if '/assets/sort.js' not in raw:
        raw = raw.replace(
            '</body>', '  <script defer src="../assets/sort.js"></script>\n</body>', 1
        )

    target.write_text(raw, encoding='utf-8')
    flag = '  ⚠ ' + '; '.join(problems) if problems else ''
    cov = f'  val {len(vals)}/{n}' if vals else ''
    print(f'  {slug:14} {n} players  avg {avg:.1f}{cov}{flag}')
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
    print('Done. Now run: python3 scripts/extract_teams.py && python3 build.py')


if __name__ == '__main__':
    main()
