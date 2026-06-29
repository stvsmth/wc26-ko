#!/usr/bin/env python3
"""Mini static-site generator for WC2026 match comparisons.

Reads data/teams.toml + data/rounds/*.toml and writes one side-by-side comparison
page per match plus a bracket index into compare/. Rebuild = re-run this script;
it owns compare/ and clears it each run. Stdlib only (tomllib, zoneinfo).

    python3 build.py
"""

import functools
import hashlib
import html
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# tomllib hands back plain dicts; these aliases name the shapes we pass around.
Team = dict[str, Any]
Match = dict[str, Any]
Round = dict[str, Any]
Teams = dict[str, Team]
Kickoff = tuple[str | None, str | None]

ROOT = Path(__file__).resolve().parent
TEAMS_FILE = ROOT / 'data' / 'teams.toml'
ROUNDS_DIR = ROOT / 'data' / 'rounds'
OUT_DIR = ROOT / 'compare'

CONF_LABELS = {
    'uefa': 'UEFA',
    'conmebol': 'CONMEBOL',
    'concacaf': 'CONCACAF',
    'caf': 'CAF',
    'afc': 'AFC',
    'ofc': 'OFC',
}

# Inlined into every page <head> before the external stylesheet so the
# confederation accent colors are defined on first paint — without this the
# accent vars resolve to the --blue fallback until style.css loads (a load-time
# blue flash). Keep in sync with the :root block in style.css.
CONF_VARS_STYLE = (
    '<style>:root{--conf-uefa:#3d7bf0;--conf-conmebol:#e8b54a;'
    '--conf-concacaf:#e3402f;--conf-caf:#1fa463;--conf-afc:#9b59d0;'
    '--conf-ofc:#16b6c4;--blue:#3d7bf0}</style>'
)

# flag-icons used to be pulled in via `@import` at the top of style.css, which
# serialized the CDN fetch *before* style.css's own rules could apply — delaying
# the --conf-*/:root block and reintroducing the load-time flash on a slow CDN.
# Load it as a parallel <link> instead so style.css applies without waiting on
# the CDN. Absolute URL, so the same string works at every page depth.
FLAG_ICONS_LINK = (
    '<link rel="stylesheet" '
    'href="https://cdn.jsdelivr.net/npm/flag-icons@7.5.0/css/flag-icons.min.css">'
)


@functools.cache
def asset_url(rel: str) -> str:
    """Cache-busting href for a compare/-relative asset: `../<rel>?v=<hash8>`, the
    hash taken over the file's *contents* so the URL changes only when the bytes
    do — an unchanged asset keeps its cached entry across rebuilds (content-keyed,
    not build-timestamp-keyed). GitHub Pages gives no header control, so a
    fingerprinted URL is the only way a returning visitor on a freshly built page
    never pairs it with a stale CSS/JS from cache. The query string needs no file
    on disk; the server still serves `rel`. Only the generated compare/ pages (one
    level deep, hence `../`) link these; hand-authored index.html and teams/*.html
    keep plain hrefs and self-heal via the 10-min GitHub Pages ETag revalidation.
    `@cache` reads + hashes each asset once for the whole build, off the import
    path so importing build.py (e.g. in tests) does no I/O."""
    digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()[:8]
    return f'../{rel}?v={digest}'


# slug -> flag-icons code (ISO 3166-1 alpha-2, lowercase). England is not an ISO
# country: its St George's Cross is the gb-eng subdivision flag, NOT gb (Union Jack).
FLAG_CODES = {
    'algeria': 'dz',
    'argentina': 'ar',
    'australia': 'au',
    'austria': 'at',
    'belgium': 'be',
    'bosnia': 'ba',
    'brazil': 'br',
    'canada': 'ca',
    'cape-verde': 'cv',
    'colombia': 'co',
    'congo-dr': 'cd',
    'croatia': 'hr',
    'ecuador': 'ec',
    'egypt': 'eg',
    'england': 'gb-eng',
    'france': 'fr',
    'germany': 'de',
    'ghana': 'gh',
    'ivory-coast': 'ci',
    'japan': 'jp',
    'mexico': 'mx',
    'morocco': 'ma',
    'netherlands': 'nl',
    'norway': 'no',
    'paraguay': 'py',
    'portugal': 'pt',
    'senegal': 'sn',
    'south-africa': 'za',
    'spain': 'es',
    'sweden': 'se',
    'switzerland': 'ch',
    'usa': 'us',
}


def die(msg: str) -> None:
    sys.exit(f'build.py: error: {msg}')


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def accent(conf: str) -> str:
    return f'var(--conf-{conf})'


def conf_label(conf: str) -> str:
    return CONF_LABELS.get(conf, conf.upper())


# Market values are Transfermarkt estimates; stamp the snapshot they reflect so
# the footnote can stay honest about how current the figures are.
MV_SNAPSHOT = 'Jun 2026'


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


def squad_value(team: Team) -> tuple[int, int, int]:
    """(total EUR, players with a value, squad size) — value is omitted where
    Transfermarkt has no listing, so coverage is reported alongside the total."""
    players: list[dict[str, Any]] = team.get('players', [])
    vals = [p['value'] for p in players if p.get('value')]
    return sum(vals), len(vals), len(players)


def mv_cell(tot: int, cov: int, n: int) -> str:
    """One team's market-value comparison cell: the total with a 'cov of n'
    coverage note, or '—' when Transfermarkt lists no values for the squad."""
    return f'{fmt_value(tot)}<small>{cov} of {n}</small>' if cov else '—'


def flag(team: Team) -> str:
    code = FLAG_CODES.get(team['slug'])
    if not code:
        die(f'no flag code for team slug {team["slug"]!r} (add to FLAG_CODES)')
    return f'<span class="fi fi-{code} flag" aria-hidden="true"></span>'


# ---------- data loading + validation ----------


def load_teams() -> Teams:
    if not TEAMS_FILE.exists():
        die(f'{TEAMS_FILE} not found — run scripts/extract_teams.py first')
    with TEAMS_FILE.open('rb') as fh:
        teams: Teams = tomllib.load(fh)
    for slug, t in teams.items():
        t.setdefault('slug', slug)
    return teams


def load_rounds() -> list[Round]:
    rounds: list[Round] = []
    for path in sorted(ROUNDS_DIR.glob('*.toml')):
        with path.open('rb') as fh:
            data: Round = tomllib.load(fh)
        data['_file'] = path.name
        rounds.append(data)
    if not rounds:
        die(f'no round files found in {ROUNDS_DIR}')
    return rounds


def parse_kickoff(match: Match, where: str) -> Kickoff:
    """Return (utc_iso, venue_local_str) or (None, None) if no kickoff set."""
    iso = match.get('kickoff_utc')
    if not iso:
        return None, None
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except ValueError:
        die(f'{where}: bad kickoff_utc {iso!r}')
    venue_local = None
    tzname = match.get('tz')
    if tzname:
        try:
            local = dt.astimezone(ZoneInfo(tzname))
        except ZoneInfoNotFoundError:
            die(f'{where}: unknown tz {tzname!r}')
        venue_local = local.strftime('%a, %b %-d, %-I:%M %p %Z')
    return dt.isoformat().replace('+00:00', 'Z'), venue_local


def validate(match: Match, teams: Teams, where: str, seen: set[frozenset[str]]) -> None:
    for side in ('home', 'away'):
        slug = match.get(side)
        if not slug:
            die(f"{where}: missing '{side}'")
        if slug not in teams:
            die(f'{where}: unknown team slug {slug!r} (not in teams.toml)')
    pair = frozenset((match['home'], match['away']))
    if pair in seen:
        die(f'{where}: duplicate pairing {match["home"]} vs {match["away"]}')
    seen.add(pair)


# ---------- rendering ----------


def match_slug(match: Match) -> str:
    return f'{match["home"]}-vs-{match["away"]}'


def kickoff_time_el(utc_iso: str, venue_local: str | None) -> str:
    """The <time class="kickoff"> element: holds venue-local text as the no-JS
    fallback; times.js upgrades it to the viewer's local zone client-side."""
    venue_attr = f' data-venue-time="{esc(venue_local)}"' if venue_local else ''
    return (
        f'<time class="kickoff" datetime="{esc(utc_iso)}" '
        f'data-kickoff="{esc(utc_iso)}"{venue_attr}>{esc(venue_local or "kickoff time")}'
        f' <span class="tznote">venue time</span></time>'
    )


def when_html(
    utc_iso: str | None, venue_local: str | None, venue: str | None, city: str | None
) -> str:
    """Kickoff line for a comparison page: the <time> element plus venue/city."""
    place = ' · '.join(p for p in (venue, city) if p)
    venue_el = f'<span class="venue">{esc(place)}</span>' if place else ''
    if not utc_iso:
        return f'<span class="tbd">Date &amp; venue TBD</span> {venue_el}'.strip()
    return f'{kickoff_time_el(utc_iso, venue_local)} {venue_el}'.strip()


def squad_html(team: Team) -> str:
    players: list[dict[str, Any]] = team.get('players', [])
    rows = []
    for p in players:
        cap = '<span class="cap">(C)</span>' if p.get('captain') else ''
        v = p.get('value')
        val_cell = (
            f'<td class="cs-value" data-eur="{v}">{fmt_value(v)}</td>'
            if v
            else '<td class="cs-value nodata">—</td>'
        )
        rows.append(
            '<tr>'
            f'<td class="cs-shirt">{esc(p.get("num", ""))}</td>'
            f'<td><span class="pos pos-{esc(p["pos"])}">{esc(p["pos"])}</span></td>'
            f'<td class="cs-name" data-sort="{esc(p["name"].lower())}">{esc(p["name"])}{cap}'
            f'<div class="cs-club">{esc(p["club"])}</div></td>'
            f'<td class="cs-age">{esc(p.get("age", ""))}</td>'
            f'<td class="cs-caps">{esc(p.get("caps", 0))}</td>'
            f'{val_cell}'
            '</tr>'
        )
    return (
        f'<div class="cmp-squad" style="--accent:{accent(team["conf"])}">'
        f'<h2><span class="dot"></span>{esc(team["name"])} · squad ({len(players)})</h2>'
        '<table class="sortable"><thead><tr>'
        '<th class="th-shirt" data-sort-type="num">#</th><th class="th-pos"></th>'
        '<th data-sort-type="text">Player</th>'
        '<th class="th-num" data-sort-type="num">Age</th>'
        '<th class="th-num" data-sort-type="num">Caps</th>'
        '<th class="th-num" data-sort-type="num">Value</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        f'<p class="cmp-profile"><a href="../{esc(team["profile"])}">'
        f'Full {esc(team["name"])} profile →</a></p></div>'
    )


def h2h_row(label: str, a_val: str, b_val: str, a_win: bool = False, b_win: bool = False) -> str:
    aw = ' win' if a_win else ''
    bw = ' win' if b_win else ''
    return (
        '<div class="h2h-row">'
        f'<div class="h2h-a{aw}">{a_val}</div>'
        f'<div class="h2h-k">{esc(label)}</div>'
        f'<div class="h2h-b{bw}">{b_val}</div></div>'
    )


def last_update_footer(build_ts: str) -> str:
    """Footer <time> stamped with the build instant; times.js upgrades the visible
    text to the viewer's local zone, with the UTC render as the no-JS fallback."""
    shown = datetime.fromisoformat(build_ts).strftime('%Y-%m-%d %H:%M UTC')
    return (
        f'<footer><p>Last update: <time class="last-update" datetime="{esc(build_ts)}" '
        f'data-last-update="{esc(build_ts)}">{shown}</time></p></footer>'
    )


def render_match(match: Match, teams: Teams, round_name: str, footer: str) -> str:
    a, b = teams[match['home']], teams[match['away']]
    utc_iso, venue_local = match['_kick']

    rows: list[str] = [
        h2h_row(
            'FIFA rank',
            f'#{esc(a["fifa_rank"])}',
            f'#{esc(b["fifa_rank"])}',
            a_win=a['fifa_rank'] < b['fifa_rank'],
            b_win=b['fifa_rank'] < a['fifa_rank'],
        ),
        h2h_row('Confederation', esc(conf_label(a['conf'])), esc(conf_label(b['conf']))),
        h2h_row(
            'Head coach',
            f'{esc(a["coach"])}<small>{esc(a.get("coach_since", ""))}</small>',
            f'{esc(b["coach"])}<small>{esc(b.get("coach_since", ""))}</small>',
        ),
        h2h_row('Group result', esc(a['group_result']), esc(b['group_result'])),
        h2h_row('Squad avg age', esc(a['avg_age']), esc(b['avg_age'])),
        h2h_row('Squad size', esc(a['squad_size']), esc(b['squad_size'])),
    ]

    # Squad market value: show the row only if at least one side has values, and
    # only declare a winner when *both* do (comparing against partial data lies).
    a_tot, a_cov, a_n = squad_value(a)
    b_tot, b_cov, b_n = squad_value(b)
    note = ''
    if a_cov or b_cov:
        comparable = bool(a_cov and b_cov)
        rows.append(
            h2h_row(
                'Squad market value',
                mv_cell(a_tot, a_cov, a_n),
                mv_cell(b_tot, b_cov, b_n),
                a_win=comparable and a_tot > b_tot,
                b_win=comparable and b_tot > a_tot,
            )
        )
        note = (
            '<p class="cmp-note">Player values are Transfermarkt market-value '
            f'estimates (EUR), as of {MV_SNAPSHOT}. “—” = no public listing.</p>'
        )

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="{asset_url('favicon.svg')}">
<title>{esc(a['name'])} vs {esc(b['name'])} — {esc(round_name)} · WC2026</title>
{CONF_VARS_STYLE}{FLAG_ICONS_LINK}<link rel="stylesheet" href="{asset_url('style.css')}">
<link rel="stylesheet" href="{asset_url('assets/compare.css')}"></head><body>
<div class="wrap"><a class="back" href="index.html">← {esc(round_name)} bracket</a>
  <header class="cmp-top">
    <div class="cmp-round">{esc(round_name)} · match comparison</div>
    <div class="cmp-title">
      <div class="side" style="--accent:{accent(a['conf'])}">
        <div class="accentbar"></div>
        <div class="conf">{flag(a)}{esc(conf_label(a['conf']))} · #{esc(a['fifa_rank'])}</div>
        <h1 class="display">{esc(a['name'])}</h1>
      </div>
      <div class="vs">vs</div>
      <div class="side right" style="--accent:{accent(b['conf'])}">
        <div class="accentbar"></div>
        <div class="conf">{flag(b)}{esc(conf_label(b['conf']))} · #{esc(b['fifa_rank'])}</div>
        <h1 class="display">{esc(b['name'])}</h1>
      </div>
    </div>
    <p class="cmp-when">{when_html(utc_iso, venue_local, match.get('venue'), match.get('city'))}</p>
  </header>
  <section class="h2h">{''.join(rows)}</section>
  <section class="cmp-squads">{squad_html(a)}{squad_html(b)}</section>
  {note}
  {footer}
</div>
<script defer src="{asset_url('assets/times.js')}"></script>
<script defer src="{asset_url('assets/sort.js')}"></script>
</body></html>
"""


def render_index(rounds: list[Round], teams: Teams, footer: str) -> str:
    cards: list[str] = []
    for rnd in rounds:
        for match in rnd['_matches']:
            a, b = teams[match['home']], teams[match['away']]
            utc_iso, venue_local = match['_kick']
            if utc_iso:
                when = kickoff_time_el(utc_iso, venue_local)
            else:
                when = '<span class="tbd">Date &amp; venue TBD</span>'
            cards.append(
                f'<a class="match-card" href="{esc(match_slug(match))}.html">'
                '<div class="mc-teams">'
                f'<div class="mc-side" style="--accent:{accent(a["conf"])}">'
                f'<div class="mc-bar"></div>'
                f'<div class="mc-rank">{flag(a)}{esc(conf_label(a["conf"]))} · #{esc(a["fifa_rank"])}</div>'
                f'<div class="mc-name display">{esc(a.get("short") or a["name"])}</div></div>'
                '<div class="mc-vs">vs</div>'
                f'<div class="mc-side right" style="--accent:{accent(b["conf"])}">'
                f'<div class="mc-bar"></div>'
                f'<div class="mc-rank">{flag(b)}{esc(conf_label(b["conf"]))} · #{esc(b["fifa_rank"])}</div>'
                f'<div class="mc-name display">{esc(b.get("short") or b["name"])}</div></div>'
                '</div>'
                f'<div class="mc-when">{when}</div></a>'
            )
    round_titles = ' · '.join(r['round'] for r in rounds)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="{asset_url('favicon.svg')}">
<title>Match comparisons — WC2026</title>
{CONF_VARS_STYLE}{FLAG_ICONS_LINK}<link rel="stylesheet" href="{asset_url('style.css')}">
<link rel="stylesheet" href="{asset_url('assets/compare.css')}"></head><body>
<div class="wrap">
  <header class="bracket-head">
    <div class="kicker"><span class="bar"></span>Head-to-head</div>
    <h1 class="display">Match Comparisons</h1>
    <p class="sub">Side-by-side breakdowns for each knockout tie — FIFA rank, coach,
    group result, squad age and key players. Kickoffs render in your local timezone.
    <a href="../index.html" style="color:var(--ink-dim);text-decoration:underline">← All 32 teams</a></p>
  </header>
  <div class="section-label">{esc(round_titles)}</div>
  <div class="match-grid">{''.join(cards)}</div>
  {footer}
</div>
<script defer src="{asset_url('assets/times.js')}"></script>
</body></html>
"""


def main() -> None:
    footer = last_update_footer(datetime.now(ZoneInfo('UTC')).isoformat())
    teams = load_teams()
    rounds = load_rounds()

    total = 0
    for rnd in rounds:
        seen: set[frozenset[str]] = set()
        matches: list[Match] = rnd.get('match', [])
        for i, match in enumerate(matches):
            where = f'{rnd["_file"]} match #{i + 1}'
            validate(match, teams, where, seen)
            match['_kick'] = parse_kickoff(match, where)
        rnd['_matches'] = matches
        total += len(matches)

    OUT_DIR.mkdir(exist_ok=True)
    for old in OUT_DIR.glob('*.html'):
        old.unlink()

    for rnd in rounds:
        for match in rnd['_matches']:
            page = render_match(match, teams, rnd['round'], footer)
            (OUT_DIR / f'{match_slug(match)}.html').write_text(page, encoding='utf-8')

    (OUT_DIR / 'index.html').write_text(render_index(rounds, teams, footer), encoding='utf-8')

    print(f'Built {total} comparison page(s) + index into {OUT_DIR.relative_to(ROOT)}/')
    for rnd in rounds:
        print(f'  {rnd["round"]} ({rnd["_file"]}): {len(rnd["_matches"])} matches')


if __name__ == '__main__':
    main()
