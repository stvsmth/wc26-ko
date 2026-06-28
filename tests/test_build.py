"""Pure-logic guards for build.py — the branching/parsing that ty can't see.

Rendering helpers that just interpolate strings into a fixed HTML shell are left
to a spot-check of the built pages (see CLAUDE.md); these cover the parts with
real decisions: kickoff parsing, match validation, and the flag-code invariant.
"""

import pytest

import build


# ---------- parse_kickoff ----------


def test_parse_kickoff_absent():
    assert build.parse_kickoff({}, 'where') == (None, None)


def test_parse_kickoff_valid_with_tz():
    utc, venue = build.parse_kickoff(
        {'kickoff_utc': '2026-07-04T19:00:00Z', 'tz': 'America/New_York'}, 'where'
    )
    assert utc == '2026-07-04T19:00:00Z', 'UTC should normalize back to a Z suffix'
    # Venue-local string is rendered via glibc %-d/%-I directives — assert it
    # produced *something* with the zone abbreviation (EDT in July, not UTC).
    assert venue and 'EDT' in venue


def test_parse_kickoff_no_tz_has_no_venue_local():
    utc, venue = build.parse_kickoff({'kickoff_utc': '2026-07-04T19:00:00Z'}, 'where')
    assert utc == '2026-07-04T19:00:00Z'
    assert venue is None


def test_parse_kickoff_bad_iso_dies():
    with pytest.raises(SystemExit):
        build.parse_kickoff({'kickoff_utc': 'not-a-date'}, 'where')


def test_parse_kickoff_unknown_tz_dies():
    with pytest.raises(SystemExit):
        build.parse_kickoff(
            {'kickoff_utc': '2026-07-04T19:00:00Z', 'tz': 'Mars/Olympus_Mons'}, 'where'
        )


# ---------- validate ----------

TEAMS = {'alpha': {'slug': 'alpha'}, 'beta': {'slug': 'beta'}, 'gamma': {'slug': 'gamma'}}


def test_validate_missing_side_dies():
    with pytest.raises(SystemExit):
        build.validate({'home': 'alpha'}, TEAMS, 'where', set())


def test_validate_unknown_slug_dies():
    with pytest.raises(SystemExit):
        build.validate({'home': 'alpha', 'away': 'nobody'}, TEAMS, 'where', set())


def test_validate_duplicate_pairing_is_symmetric():
    """alpha-vs-beta and beta-vs-alpha are the same tie (frozenset key)."""
    seen: set = set()
    build.validate({'home': 'alpha', 'away': 'beta'}, TEAMS, 'm1', seen)
    with pytest.raises(SystemExit):
        build.validate({'home': 'beta', 'away': 'alpha'}, TEAMS, 'm2', seen)


def test_validate_distinct_pairings_pass():
    seen: set = set()
    build.validate({'home': 'alpha', 'away': 'beta'}, TEAMS, 'm1', seen)
    build.validate({'home': 'alpha', 'away': 'gamma'}, TEAMS, 'm2', seen)


# ---------- FLAG_CODES completeness ----------


def test_every_team_has_a_flag_code():
    """build.flag() dies on an unmapped slug — catch that at test time instead."""
    teams = build.load_teams()
    missing = sorted(slug for slug in teams if slug not in build.FLAG_CODES)
    assert not missing, f'teams missing from FLAG_CODES: {missing}'


# ---------- escaping ----------


def test_squad_html_escapes_player_fields():
    team = {
        'slug': 'x',
        'name': 'X',
        'conf': 'uefa',
        'profile': 'teams/x.html',
        'players': [
            {
                'num': 7,
                'name': 'A<b> & "C"',
                'pos': 'FW',
                'club': 'Club & Co',
                'age': 25,
                'caps': 1,
            },
        ],
    }
    out = build.squad_html(team)
    assert 'A<b>' not in out, 'raw markup leaked into squad HTML'
    assert '&lt;b&gt;' in out and '&amp;' in out
