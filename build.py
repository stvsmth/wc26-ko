#!/usr/bin/env python3
"""Mini static-site generator for WC2026 match comparisons.

Reads data/teams.toml + data/rounds/*.toml and writes one side-by-side comparison
page per match plus a bracket index into compare/. Rebuild = re-run this script;
it owns compare/ and clears it each run. Stdlib only (tomllib, zoneinfo).

    python3 build.py
"""
import html
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent
TEAMS_FILE = ROOT / "data" / "teams.toml"
ROUNDS_DIR = ROOT / "data" / "rounds"
OUT_DIR = ROOT / "compare"

CONF_LABELS = {
    "uefa": "UEFA", "conmebol": "CONMEBOL", "concacaf": "CONCACAF",
    "caf": "CAF", "afc": "AFC", "ofc": "OFC",
}


def die(msg: str) -> None:
    sys.exit(f"build.py: error: {msg}")


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def accent(conf: str) -> str:
    return f"var(--conf-{conf})"


def conf_label(conf: str) -> str:
    return CONF_LABELS.get(conf, conf.upper())


# ---------- data loading + validation ----------

def load_teams() -> dict:
    if not TEAMS_FILE.exists():
        die(f"{TEAMS_FILE} not found — run scripts/extract_teams.py first")
    with TEAMS_FILE.open("rb") as fh:
        teams = tomllib.load(fh)
    for slug, t in teams.items():
        t.setdefault("slug", slug)
    return teams


def load_rounds() -> list:
    rounds = []
    for path in sorted(ROUNDS_DIR.glob("*.toml")):
        with path.open("rb") as fh:
            data = tomllib.load(fh)
        data["_file"] = path.name
        rounds.append(data)
    if not rounds:
        die(f"no round files found in {ROUNDS_DIR}")
    return rounds


def parse_kickoff(match: dict, where: str):
    """Return (utc_iso, venue_local_str) or (None, None) if no kickoff set."""
    iso = match.get("kickoff_utc")
    if not iso:
        return None, None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        die(f"{where}: bad kickoff_utc {iso!r}")
    venue_local = None
    tzname = match.get("tz")
    if tzname:
        try:
            local = dt.astimezone(ZoneInfo(tzname))
        except ZoneInfoNotFoundError:
            die(f"{where}: unknown tz {tzname!r}")
        venue_local = local.strftime("%a, %b %-d, %-I:%M %p %Z")
    return dt.isoformat().replace("+00:00", "Z"), venue_local


def validate(match: dict, teams: dict, where: str, seen: set) -> None:
    for side in ("home", "away"):
        slug = match.get(side)
        if not slug:
            die(f"{where}: missing '{side}'")
        if slug not in teams:
            die(f"{where}: unknown team slug {slug!r} (not in teams.toml)")
    pair = frozenset((match["home"], match["away"]))
    if pair in seen:
        die(f"{where}: duplicate pairing {match['home']} vs {match['away']}")
    seen.add(pair)


# ---------- rendering ----------

def match_slug(match: dict) -> str:
    return f"{match['home']}-vs-{match['away']}"


def when_html(utc_iso, venue_local, venue, city) -> str:
    """Kickoff line: <time> holds venue-local text (no-JS fallback); times.js
    upgrades it to the viewer's local zone."""
    place = " · ".join(p for p in (venue, city) if p)
    if not utc_iso:
        loc = f'<span class="venue">{esc(place)}</span>' if place else ""
        return f'<span class="tbd">Date &amp; venue TBD</span> {loc}'.strip()
    fallback = venue_local or "kickoff time"
    venue_attr = f' data-venue-time="{esc(venue_local)}"' if venue_local else ""
    time_el = (
        f'<time class="kickoff" datetime="{esc(utc_iso)}" '
        f'data-kickoff="{esc(utc_iso)}"{venue_attr}>{esc(fallback)}'
        f' <span class="tznote">venue time</span></time>'
    )
    venue_el = f'<span class="venue">{esc(place)}</span>' if place else ""
    return f"{time_el} {venue_el}".strip()


def squad_html(team: dict) -> str:
    players = team.get("players", [])
    rows = []
    for p in players:
        cap = '<span class="cap">(C)</span>' if p.get("captain") else ""
        rows.append(
            "<tr>"
            f'<td><span class="pos pos-{esc(p["pos"])}">{esc(p["pos"])}</span></td>'
            f'<td class="cs-name">{esc(p["name"])}{cap}'
            f'<div class="cs-club">{esc(p["club"])}</div></td>'
            f'<td class="cs-age">{esc(p.get("age", ""))}</td>'
            f'<td class="cs-caps">{esc(p.get("caps", 0))}</td>'
            "</tr>"
        )
    return (
        f'<div class="cmp-squad" style="--accent:{accent(team["conf"])}">'
        f'<h2><span class="dot"></span>{esc(team["name"])} · squad ({len(players)})</h2>'
        '<table><thead><tr><th class="th-pos"></th><th>Player</th>'
        '<th class="th-num">Age</th><th class="th-num">Caps</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        f'<p class="cmp-profile"><a href="../{esc(team["profile"])}">'
        f'Full {esc(team["name"])} profile →</a></p></div>'
    )


def h2h_row(label: str, a_val: str, b_val: str, a_win=False, b_win=False) -> str:
    aw = " win" if a_win else ""
    bw = " win" if b_win else ""
    return (
        '<div class="h2h-row">'
        f'<div class="h2h-a{aw}">{a_val}</div>'
        f'<div class="h2h-k">{esc(label)}</div>'
        f'<div class="h2h-b{bw}">{b_val}</div></div>'
    )


def render_match(match: dict, teams: dict, round_name: str) -> str:
    a, b = teams[match["home"]], teams[match["away"]]
    utc_iso, venue_local = match["_kick"]

    rows = [
        h2h_row("FIFA rank", f"#{esc(a['fifa_rank'])}", f"#{esc(b['fifa_rank'])}",
                a_win=a["fifa_rank"] < b["fifa_rank"],
                b_win=b["fifa_rank"] < a["fifa_rank"]),
        h2h_row("Confederation", esc(conf_label(a["conf"])), esc(conf_label(b["conf"]))),
        h2h_row("Head coach",
                f'{esc(a["coach"])}<small>{esc(a.get("coach_since",""))}</small>',
                f'{esc(b["coach"])}<small>{esc(b.get("coach_since",""))}</small>'),
        h2h_row("Group result", esc(a["group_result"]), esc(b["group_result"])),
        h2h_row("Squad avg age", esc(a["avg_age"]), esc(b["avg_age"])),
        h2h_row("Squad size", esc(a["squad_size"]), esc(b["squad_size"])),
    ]

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(a['name'])} vs {esc(b['name'])} — {esc(round_name)} · WC2026</title>
<link rel="stylesheet" href="../style.css">
<link rel="stylesheet" href="../assets/compare.css"></head><body>
<div class="wrap"><a class="back" href="index.html">← {esc(round_name)} bracket</a>
  <header class="cmp-top">
    <div class="cmp-round">{esc(round_name)} · match comparison</div>
    <div class="cmp-title">
      <div class="side" style="--accent:{accent(a['conf'])}">
        <div class="accentbar"></div>
        <h1 class="display">{esc(a['name'])}</h1>
        <div class="conf">{esc(conf_label(a['conf']))} · #{esc(a['fifa_rank'])}</div>
      </div>
      <div class="vs">vs</div>
      <div class="side right" style="--accent:{accent(b['conf'])}">
        <div class="accentbar"></div>
        <h1 class="display">{esc(b['name'])}</h1>
        <div class="conf">{esc(conf_label(b['conf']))} · #{esc(b['fifa_rank'])}</div>
      </div>
    </div>
    <p class="cmp-when">{when_html(utc_iso, venue_local, match.get('venue'), match.get('city'))}</p>
  </header>
  <section class="h2h">{''.join(rows)}</section>
  <section class="cmp-squads">{squad_html(a)}{squad_html(b)}</section>
  <footer><p>Comparison auto-generated by build.py from data/teams.toml and
  data/rounds/. Kickoff shown in your browser's local timezone; FIFA rank as of
  11 Jun 2026. (C) = captain.</p></footer>
</div>
<script defer src="../assets/times.js"></script>
</body></html>
"""


def render_index(rounds: list, teams: dict) -> str:
    cards = []
    for rnd in rounds:
        for match in rnd["_matches"]:
            a, b = teams[match["home"]], teams[match["away"]]
            utc_iso, venue_local = match["_kick"]
            if utc_iso:
                when = (
                    f'<time class="kickoff" datetime="{esc(utc_iso)}" '
                    f'data-kickoff="{esc(utc_iso)}"'
                    f'{f" data-venue-time=\"{esc(venue_local)}\"" if venue_local else ""}>'
                    f'{esc(venue_local or "kickoff time")}'
                    f' <span class="tznote">venue time</span></time>'
                )
            else:
                when = '<span class="tbd">Date &amp; venue TBD</span>'
            cards.append(
                f'<a class="match-card" href="{esc(match_slug(match))}.html">'
                '<div class="mc-teams">'
                f'<div class="mc-side" style="--accent:{accent(a["conf"])}">'
                f'<div class="mc-bar"></div>'
                f'<div class="mc-rank">{esc(conf_label(a["conf"]))} · #{esc(a["fifa_rank"])}</div>'
                f'<div class="mc-name display">{esc(a.get("short") or a["name"])}</div></div>'
                '<div class="mc-vs">vs</div>'
                f'<div class="mc-side right" style="--accent:{accent(b["conf"])}">'
                f'<div class="mc-bar"></div>'
                f'<div class="mc-rank">{esc(conf_label(b["conf"]))} · #{esc(b["fifa_rank"])}</div>'
                f'<div class="mc-name display">{esc(b.get("short") or b["name"])}</div></div>'
                '</div>'
                f'<div class="mc-when">{when}</div></a>'
            )
    round_titles = " · ".join(r["round"] for r in rounds)
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Match comparisons — WC2026</title>
<link rel="stylesheet" href="../style.css">
<link rel="stylesheet" href="../assets/compare.css"></head><body>
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
  <footer><p>Auto-generated by build.py. Add fixtures in data/rounds/ (R16, R8 …)
  and rerun to extend this bracket.</p></footer>
</div>
<script defer src="../assets/times.js"></script>
</body></html>
"""


def main() -> None:
    teams = load_teams()
    rounds = load_rounds()

    total = 0
    for rnd in rounds:
        seen = set()
        matches = rnd.get("match", [])
        for i, match in enumerate(matches):
            where = f"{rnd['_file']} match #{i + 1}"
            validate(match, teams, where, seen)
            match["_kick"] = parse_kickoff(match, where)
        rnd["_matches"] = matches
        total += len(matches)

    OUT_DIR.mkdir(exist_ok=True)
    for old in OUT_DIR.glob("*.html"):
        old.unlink()

    for rnd in rounds:
        for match in rnd["_matches"]:
            page = render_match(match, teams, rnd["round"])
            (OUT_DIR / f"{match_slug(match)}.html").write_text(page, encoding="utf-8")

    (OUT_DIR / "index.html").write_text(render_index(rounds, teams), encoding="utf-8")

    print(f"Built {total} comparison page(s) + index into {OUT_DIR.relative_to(ROOT)}/")
    for rnd in rounds:
        print(f"  {rnd['round']} ({rnd['_file']}): {len(rnd['_matches'])} matches")


if __name__ == "__main__":
    main()
