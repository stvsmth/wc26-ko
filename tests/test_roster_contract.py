"""The apply_rosters <-> extract_teams HTML contract.

apply_rosters.py *writes* the squad table; extract_teams.py *parses it back*.
They are coupled only by the markup shape — a template change on one side that
isn't mirrored on the other can't be caught by the type checker. These tests
feed apply_rosters' output straight into extract_teams' BeautifulSoup parsers,
so drift fails here instead of silently dropping data on the next scaffold.
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup

import apply_rosters
import extract_teams
from apply_rosters import AVG_PREFIX, VALUE_FACT_KEY

DUMMY = Path('<test>')


def soup(fragment: str) -> BeautifulSoup:
    return BeautifulSoup(fragment, 'lxml')


# Mix of players with and without a market value: a missing value must round-trip
# back to None, not get confused with a real figure.
SQUAD = [
    {
        'num': 1,
        'name': 'Alex Keeper',
        'pos': 'GK',
        'club': 'Club A (ENG)',
        'age': 30,
        'caps': 40,
        'value': 5_000_000,
    },
    {
        'num': 4,
        'name': 'Bo Back',
        'pos': 'DF',
        'club': 'Club B (ESP)',
        'age': 27,
        'caps': 22,
        'value': 12_500_000,
    },
    {
        'num': 8,
        'name': 'Cy Mid',
        'pos': 'MF',
        'club': 'Club C (GER)',
        'age': 24,
        'caps': 15,
        'value': 80_000_000,
        'captain': True,
    },
    {'num': 9, 'name': 'Di Forward', 'pos': 'FW', 'club': 'Club D (ITA)', 'age': 22, 'caps': 9},
]


def test_squad_rows_round_trip():
    """Every field apply_rosters writes is recovered by parse_players."""
    players = extract_teams.parse_players(soup(apply_rosters.squad_block(SQUAD)), DUMMY)

    assert len(players) == len(SQUAD), 'parse_players did not recover every emitted row'

    by_num = {p['num']: p for p in SQUAD}
    for got in players:
        src = by_num[got['num']]
        assert got['pos'] == src['pos']
        assert got['name'] == src['name']
        assert got['club'] == src['club']
        assert got['age'] == src['age']
        assert got['caps'] == src['caps']
        assert got['captain'] == bool(src.get('captain'))
        # data-eur carries the exact value losslessly; absent => None.
        assert got['value'] == src.get('value')


def test_avg_age_factstrip_round_trip():
    """The avg-age factstrip apply_rosters writes is parsed back by parse_facts."""
    n = len(SQUAD)
    avg = sum(p['age'] for p in SQUAD) / n
    # Mirror apply_rosters.AVG_RE.subn's replacement, inside the page's .fact wrapper.
    inner = f'{AVG_PREFIX}{avg:.1f}\n          <small>{n}-player squad</small>'
    fragment = f'<div class="fact">{inner}</div></div>'

    facts = extract_teams.parse_facts(soup(fragment))
    assert 'Squad avg age' in facts, 'parse_facts no longer matches the avg-age factstrip'
    avg_raw, squad_sub = facts['Squad avg age']
    assert float(avg_raw) == round(avg, 1)

    squad_size = re.search(r'(\d+)-player', squad_sub)
    assert squad_size is not None and int(squad_size.group(1)) == n


def test_squad_value_factstrip_round_trip():
    """The squad-value fact apply_rosters splices in is parsed back by parse_facts
    and reports coverage (N of M) so a partial squad reads honestly."""
    vals = [p['value'] for p in SQUAD if p.get('value')]
    fragment = apply_rosters.value_fact_html(sum(vals), len(vals), len(SQUAD))

    facts = extract_teams.parse_facts(soup(fragment))
    assert VALUE_FACT_KEY in facts, 'parse_facts no longer matches the squad-value fact'
    value_disp, coverage = facts[VALUE_FACT_KEY]
    assert value_disp.startswith('€')
    cov = re.search(r'(\d+) of (\d+)', coverage)
    assert cov is not None
    assert int(cov.group(1)) == len(vals) and int(cov.group(2)) == len(SQUAD)


def test_value_fact_removal_is_idempotent():
    """VALUE_FACT_RE strips exactly the spliced fact, leaving avg-age intact."""
    avg_fact = f'{AVG_PREFIX}25.0\n          <small>4-player squad</small></div></div>'
    spliced = avg_fact + apply_rosters.value_fact_html(100, 2, 4)
    cleaned = apply_rosters.VALUE_FACT_RE.sub('', spliced)
    assert cleaned == avg_fact
    # A second pass is a no-op.
    assert apply_rosters.VALUE_FACT_RE.sub('', cleaned) == avg_fact
