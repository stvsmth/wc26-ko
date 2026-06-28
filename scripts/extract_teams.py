#!/usr/bin/env python3
"""One-time scaffolding helper: read the hand-authored teams/*.html profile pages
and emit data/teams.toml (per-team comparable stats + full squad).

teams.toml is a *hand-editable* artifact after this runs — build.py never rewrites
it. Re-run this only if you want to re-scaffold from the HTML. Spot-check the output.

Usage:  uv run python scripts/extract_teams.py
"""

import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

ROOT = Path(__file__).resolve().parent.parent
TEAMS_DIR = ROOT / 'teams'
OUT = ROOT / 'data' / 'teams.toml'

# Short display names for compact bracket cards (full name still used everywhere
# else). Add an entry for any team whose name overflows a fixed-width card.
SHORT_NAMES = {
    'bosnia': 'Bosnia & Herz.',
}

CONF_RE = re.compile(r'--conf-(\w+)')


def text(node: Tag) -> str:
    """Collapse a node's text to a single trimmed line (entities already decoded)."""
    return node.get_text().strip()


def need(node: Tag | None, what: str, path: Path) -> Tag:
    """Require an element; the team HTML is expected to contain each field."""
    if node is None:
        raise SystemExit(f'extract_teams: {what} not found in {path}')
    return node


def cell(parent: Tag, selector: str, path: Path) -> str:
    """Trimmed text of a required descendant element."""
    return text(need(parent.select_one(selector), selector, path))


def need_match(match: re.Match[str] | None, what: str, path: Path) -> str:
    """Require a regex match; return its first group."""
    if match is None:
        raise SystemExit(f'extract_teams: {what} not found in {path}')
    return match.group(1)


def tstr(value: str) -> str:
    """TOML-escape a string for a basic (double-quoted) key/value."""
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def parse_facts(soup: Tag) -> dict[str, tuple[str, str]]:
    """Map each `.fact` to (value, small-subtext). Value div's trailing <small>
    holds the subtext; it's split off so the value text stands alone."""
    facts: dict[str, tuple[str, str]] = {}
    for fact in soup.select('.fact'):
        key = fact.select_one('.k')
        value = fact.select_one('.v')
        if key is None or value is None:
            continue
        small = value.find('small')
        if isinstance(small, Tag):
            sub = text(small)
            small.extract()
        else:
            sub = ''
        facts[text(key)] = (text(value), sub)
    return facts


def parse_players(soup: Tag, path: Path) -> list[dict[str, Any]]:
    """Parse every `table.squad` body row into a player dict."""
    players: list[dict[str, Any]] = []
    for row in soup.select('table.squad tbody tr'):
        pname = need(row.select_one('td.pname'), 'player name cell', path)
        cap = pname.find('span', class_='cap')
        captain = cap is not None
        if isinstance(cap, Tag):
            cap.extract()
        value_cell = row.select_one('td.value-cell')
        eur = value_cell.get('data-eur') if value_cell else None
        players.append(
            {
                'num': int(cell(row, 'td.shirt-cell', path)),
                'name': text(pname),
                'pos': cell(row, 'span.pos', path),
                'club': cell(row, 'td.club', path),
                'age': int(cell(row, 'td.age-cell', path)),
                'caps': int(cell(row, 'td.num-cell', path)),
                'value': int(str(eur)) if eur else None,
                'captain': captain,
            }
        )
    return players


def extract(path: Path) -> dict[str, Any]:
    soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'lxml')
    slug = path.stem

    # conf code from the first inline `--accent:var(--conf-<conf>)` style attr.
    accent = need(soup.select_one('[style*="var(--conf-"]'), 'confederation accent', path)
    conf = need_match(CONF_RE.search(str(accent.get('style', ''))), 'confederation', path)

    facts = parse_facts(soup)
    coach, coach_since = facts.get('Head coach', ('', ''))
    group_result = facts.get('Group result', ('', ''))[0]
    avg_age_raw, squad_sub = facts.get('Squad avg age', ('', ''))
    squad_size = re.search(r'(\d+)-player', squad_sub)
    players = parse_players(soup, path)

    return {
        'slug': slug,
        'name': text(need(soup.select_one('h1.display'), 'team name', path)),
        'short': SHORT_NAMES.get(slug),
        'conf': conf,
        'fifa_rank': int(re.sub(r'\D', '', cell(soup, '.rankbadge .num', path))),
        'coach': coach,
        'coach_since': coach_since,
        'group_result': group_result,
        'avg_age': float(avg_age_raw) if avg_age_raw else 0.0,
        'squad_size': int(squad_size.group(1)) if squad_size else len(players),
        'profile': f'teams/{slug}.html',
        'blurb': text(need(soup.select_one('p.sub'), 'blurb', path)),
        'players': players,
    }


def to_toml(team: dict[str, Any]) -> str:
    out = [f'[{team["slug"]}]']
    out.append(f'name        = {tstr(team["name"])}')
    if team.get('short'):
        out.append(f'short       = {tstr(team["short"])}')
    out.append(f'conf        = {tstr(team["conf"])}')
    out.append(f'fifa_rank   = {team["fifa_rank"]}')
    out.append(f'coach       = {tstr(team["coach"])}')
    out.append(f'coach_since = {tstr(team["coach_since"])}')
    out.append(f'group_result= {tstr(team["group_result"])}')
    out.append(f'avg_age     = {team["avg_age"]}')
    out.append(f'squad_size  = {team["squad_size"]}')
    out.append(f'profile     = {tstr(team["profile"])}')
    out.append(f'blurb       = {tstr(team["blurb"])}')
    out.append('players = [')
    for p in team['players']:
        cap = ', captain = true' if p['captain'] else ''
        val = f', value = {p["value"]}' if p.get('value') else ''
        out.append(
            f'  {{ num = {p["num"]}, name = {tstr(p["name"])}, pos = {tstr(p["pos"])}, '
            f'club = {tstr(p["club"])}, age = {p["age"]}, caps = {p["caps"]}{val}{cap} }},'
        )
    out.append(']')
    return '\n'.join(out)


def main() -> None:
    teams = [extract(p) for p in sorted(TEAMS_DIR.glob('*.html'))]
    header = (
        '# Per-team comparable stats + squads, scaffolded from teams/*.html by\n'
        '# scripts/extract_teams.py. Hand-editable; build.py only reads this file.\n'
    )
    OUT.write_text(
        header + '\n' + '\n\n'.join(to_toml(t) for t in teams) + '\n',
        encoding='utf-8',
    )
    print(f'Wrote {OUT.relative_to(ROOT)} — {len(teams)} teams')
    for t in teams:
        print(
            f'  {t["slug"]:14} #{t["fifa_rank"]:<3} {t["conf"]:9} '
            f'{len(t["players"])} players  ({t["coach"]})'
        )


if __name__ == '__main__':
    main()
