"""The apply_rosters <-> extract_teams HTML contract.

apply_rosters.py *writes* the squad table; extract_teams.py *parses it back*.
They are coupled only by the markup shape — ty sees both sides as str/regex and
cannot catch a drift. These tests feed apply_rosters' output straight into
extract_teams' regexes, so a template change on one side that isn't mirrored on
the other fails here instead of silently dropping data on the next scaffold.
"""

import re

import apply_rosters
import extract_teams
from apply_rosters import AVG_PREFIX

SQUAD = [
    {'num': 1, 'name': 'Alex Keeper', 'pos': 'GK', 'club': 'Club A (ENG)', 'age': 30, 'caps': 40},
    {'num': 4, 'name': 'Bo Back', 'pos': 'DF', 'club': 'Club B (ESP)', 'age': 27, 'caps': 22},
    {
        'num': 8,
        'name': 'Cy Mid',
        'pos': 'MF',
        'club': 'Club C (GER)',
        'age': 24,
        'caps': 15,
        'captain': True,
    },
    {'num': 9, 'name': 'Di Forward', 'pos': 'FW', 'club': 'Club D (ITA)', 'age': 22, 'caps': 9},
]


def test_squad_rows_round_trip():
    """Every field apply_rosters writes is recovered by extract_teams' ROW_RE."""
    html_block = apply_rosters.squad_block(SQUAD)
    rows = extract_teams.ROW_RE.findall(html_block)

    assert len(rows) == len(SQUAD), 'ROW_RE did not match every emitted row'

    by_num = {p['num']: p for p in SQUAD}
    for num, pos, pname, club, age, caps in rows:
        src = by_num[int(num)]
        captain = bool(extract_teams.CAP_RE.search(pname))
        assert pos == src['pos']
        assert extract_teams.clean(extract_teams.CAP_RE.sub('', pname)) == src['name']
        assert extract_teams.clean(club) == src['club']
        assert int(age) == src['age']
        assert int(caps) == src['caps']
        assert captain == bool(src.get('captain'))


def test_avg_age_factstrip_round_trip():
    """The avg-age factstrip apply_rosters writes is parsed back by FACT_RE."""
    n = len(SQUAD)
    avg = sum(p['age'] for p in SQUAD) / n
    # Mirror apply_rosters.AVG_RE.subn's replacement string exactly.
    fragment = f'{AVG_PREFIX}{avg:.1f}\n          <small>{n}-player squad</small>'

    facts = {
        extract_teams.clean(k): (extract_teams.clean(v), extract_teams.clean(s))
        for k, v, s in extract_teams.FACT_RE.findall(fragment)
    }
    assert 'Squad avg age' in facts, 'FACT_RE no longer matches the avg-age factstrip'
    avg_raw, squad_sub = facts['Squad avg age']
    assert float(avg_raw) == round(avg, 1)

    squad_size = re.search(r'(\d+)-player', squad_sub)
    assert squad_size is not None and int(squad_size.group(1)) == n
