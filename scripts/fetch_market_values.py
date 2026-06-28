#!/usr/bin/env python3
"""Join Transfermarkt market values into roster TOML files (authoring-time only).

Source data: the Kaggle dataset *Football Data from Transfermarkt*
(davidcariboo/player-scores), specifically its ``players.csv``. Download it by
hand once (Kaggle account required) — it is NOT fetched at build time and the
build itself stays stdlib/offline. Point this script at the file:

    python3 scripts/fetch_market_values.py path/to/players.csv          # pilot teams
    python3 scripts/fetch_market_values.py path/to/players.csv spain    # one team
    python3 scripts/fetch_market_values.py path/to/players.csv --all    # every roster

For each roster it matches players by (normalized name) and disambiguates name
collisions by club, then writes/updates a ``value = <eur>`` line in the matching
``[[player]]`` block in place (idempotent). Players it cannot match confidently
are left without a value — that gap is meaningful — and reported for hand
resolution. After running, re-apply and rebuild:

    python3 scripts/apply_rosters.py && python3 scripts/extract_teams.py && python3 build.py

This needs only the stdlib (csv, tomllib); it is dev/authoring tooling, never
part of the build.
"""

import csv
import re
import sys
import tomllib
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
ROSTERS_DIR = ROOT / 'data' / 'rosters'

# Default pilot set (see plans/ — the wage/value feature ships on these first).
PILOT = ['usa', 'bosnia', 'argentina', 'spain', 'france', 'portugal']

# players.csv column names we read (davidcariboo/player-scores schema).
COL_NAME = 'name'
COL_VALUE = 'market_value_in_eur'
COL_CLUB = 'current_club_name'


# Latin letters that don't NFKD-decompose to ASCII + a combining mark, mapped to
# the transliteration Transfermarkt uses in its URL slugs (ø→o, æ→ae, ...).
TRANSLIT = str.maketrans(
    {'ø': 'o', 'æ': 'ae', 'œ': 'oe', 'ł': 'l', 'ð': 'd', 'þ': 'th', 'đ': 'd',
     'ı': 'i', 'ß': 'ss', 'å': 'a', 'ñ': 'n', 'ø'.upper(): 'o'}
)
NORM_RE = re.compile(r'[^a-z0-9]+')
PAREN_RE = re.compile(r'\s*\([^)]*\)\s*$')


def norm(text: str) -> str:
    """Casefold + transliterate so 'Martin Ødegaard' == 'martin odegaard' and
    "N'Golo" == 'ngolo' — matching how Transfermarkt forms its name slugs."""
    decomposed = unicodedata.normalize('NFKD', text)
    stripped = ''.join(c for c in decomposed if not unicodedata.combining(c))
    folded = stripped.casefold().translate(TRANSLIT)
    folded = folded.replace("'", '').replace('’', '')  # TM drops apostrophes
    return NORM_RE.sub(' ', folded).strip()


def club_name(roster_club: str) -> str:
    """'Atlético Madrid (ESP)' -> normalized 'atletico madrid' for overlap scoring."""
    return norm(PAREN_RE.sub('', roster_club))


def load_index(csv_path: Path) -> dict[str, list[dict[str, str]]]:
    """name (normalized) -> candidate records, keeping only rows with a value."""
    index: dict[str, list[dict[str, str]]] = {}
    with csv_path.open(encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for field in (COL_NAME, COL_VALUE):
            if field not in (reader.fieldnames or []):
                sys.exit(f'fetch_market_values: {csv_path} has no {field!r} column')
        for row in reader:
            value = (row.get(COL_VALUE) or '').strip()
            if not value or not value.isdigit() or int(value) <= 0:
                continue
            index.setdefault(norm(row[COL_NAME]), []).append(row)
    return index


def score(cand: dict[str, str], player: dict[str, Any]) -> int:
    """Higher = better match. Rewards club tokens shared with the roster entry."""
    pts = 0
    cand_club = norm(cand.get(COL_CLUB, '') or '')
    want_club = club_name(player['club'])
    if cand_club and want_club:
        shared = set(cand_club.split()) & set(want_club.split())
        pts += 3 * len(shared)
    return pts


def resolve(player: dict[str, Any], index: dict[str, list[dict[str, str]]]) -> int | None:
    """Best market value for a roster player, or None if no confident match."""
    cands = index.get(norm(player['name']))
    if not cands:
        return None
    if len(cands) == 1:
        return int(cands[0][COL_VALUE])
    ranked = sorted(cands, key=lambda c: score(c, player), reverse=True)
    top, runner = ranked[0], ranked[1]
    # Require the best candidate to beat the next on club signal; a tie means we
    # cannot tell them apart, so we decline rather than guess.
    if score(top, player) == score(runner, player):
        return None
    return int(top[COL_VALUE])


VALUE_LINE_RE = re.compile(r'^value\s*=.*\n?', re.M)
CAPS_LINE_RE = re.compile(r'^(caps\s*=.*\n)', re.M)
PROV_RE = re.compile(r'^# market values:.*\n', re.M)
PLAYER_SPLIT_RE = re.compile(r'(?m)^(?=\[\[player\]\])')
NUM_RE = re.compile(r'^num\s*=\s*(\d+)', re.M)


def apply_values(text: str, resolved: dict[int, int]) -> str:
    """Set `value = <eur>` in each [[player]] block whose num is in `resolved`.

    Idempotent: an existing value line is replaced; otherwise one is inserted
    right after the block's `caps =` line."""
    out: list[str] = []
    for chunk in PLAYER_SPLIT_RE.split(text):
        m = NUM_RE.search(chunk)
        if m and int(m.group(1)) in resolved:
            chunk = VALUE_LINE_RE.sub('', chunk)
            chunk = CAPS_LINE_RE.sub(rf'\1value = {resolved[int(m.group(1))]}\n', chunk, count=1)
        out.append(chunk)
    return ''.join(out)


def stamp_provenance(text: str, snapshot: str) -> str:
    """Prepend a provenance comment naming the value source (idempotent)."""
    line = (
        f'# market values: Transfermarkt estimates, snapshot {snapshot} '
        '(scripts/fetch_market_values.py)\n'
    )
    return line + PROV_RE.sub('', text)


def process(
    path: Path, index: dict[str, list[dict[str, str]]], snapshot: str
) -> tuple[int, list[str]]:
    text = path.read_text(encoding='utf-8')
    players: list[dict[str, Any]] = tomllib.loads(text).get('player', [])
    resolved: dict[int, int] = {}
    missing: list[str] = []
    for p in players:
        value = resolve(p, index)
        if value is None:
            missing.append(f'{p["num"]:>2} {p["name"]} ({p["club"]})')
        else:
            resolved[p['num']] = value
    if resolved:
        path.write_text(stamp_provenance(apply_values(text, resolved), snapshot), encoding='utf-8')
    return len(resolved), missing


def main() -> None:
    argv = sys.argv[1:]
    if not argv:
        sys.exit('usage: fetch_market_values.py <players.csv> [slug ...|--all]')
    csv_path = Path(argv[0])
    if not csv_path.exists():
        sys.exit(f'fetch_market_values: {csv_path} not found')
    rest = argv[1:]
    if '--all' in rest:
        slugs = [p.stem for p in sorted(ROSTERS_DIR.glob('*.toml'))]
    else:
        slugs = rest or PILOT

    index = load_index(csv_path)
    snapshot = f'{date.today():%Y-%m-%d}'
    print(f'Indexed {sum(len(v) for v in index.values())} valued players from {csv_path.name}')
    print(f'Snapshot {snapshot}. Joining {len(slugs)} roster(s):\n')

    for slug in slugs:
        path = ROSTERS_DIR / f'{slug}.toml'
        if not path.exists():
            print(f'  {slug:14} ⚠ no roster file')
            continue
        n, missing = process(path, index, snapshot)
        print(f'  {slug:14} matched {n}/26')
        for line in missing:
            print(f'       · no match: {line}')
    print('\nReview unmatched players above, then: '
          'python3 scripts/apply_rosters.py && python3 scripts/extract_teams.py && python3 build.py')


if __name__ == '__main__':
    main()
