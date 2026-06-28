#!/usr/bin/env python3
"""One-time scaffolding helper: read the hand-authored teams/*.html profile pages
and emit data/teams.toml (per-team comparable stats + full squad).

teams.toml is a *hand-editable* artifact after this runs — build.py never rewrites
it. Re-run this only if you want to re-scaffold from the HTML. Spot-check the output.

Usage:  python3 scripts/extract_teams.py
"""
import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAMS_DIR = ROOT / "teams"
OUT = ROOT / "data" / "teams.toml"

# Short display names for compact bracket cards (full name still used everywhere
# else). Add an entry for any team whose name overflows a fixed-width card.
SHORT_NAMES = {
    "bosnia": "Bosnia & Herz.",
}

CONF_RE = re.compile(r"--accent:var\(--conf-(\w+)\)")
NAME_RE = re.compile(r'<h1 class="display">(.*?)</h1>', re.S)
RANK_RE = re.compile(r'<div class="num"><small>#</small>(\d+)</div>')
SUB_RE = re.compile(r'<p class="sub"[^>]*>(.*?)</p>', re.S)
FACT_RE = re.compile(
    r'<div class="k">(.*?)</div><div class="v">(.*?)\s*<small>(.*?)</small>', re.S
)
ROW_RE = re.compile(
    r'<td class="shirt-cell">(\d+)</td>\s*<td>\s*'
    r'<span class="pos pos-(GK|DF|MF|FW)">[A-Z]+</span></td>\s*'
    r'<td class="pname">(.*?)</td>\s*'
    r'<td class="club">(.*?)</td>\s*'
    r'<td class="age-cell">(\d+)</td>\s*'
    r'<td class="num-cell">(\d+)</td>',
    re.S,
)
CAP_RE = re.compile(r'<span class="cap">.*?</span>')


def clean(text: str) -> str:
    """Strip tags/entities/whitespace from a captured HTML fragment."""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def tstr(value: str) -> str:
    """TOML-escape a string for a basic (double-quoted) key/value."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def extract(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    slug = path.stem

    facts = {clean(k): (clean(v), clean(s)) for k, v, s in FACT_RE.findall(raw)}
    coach, coach_since = facts.get("Head coach", ("", ""))
    group_result = facts.get("Group result", ("", ""))[0]
    avg_age_raw, squad_sub = facts.get("Squad avg age", ("", ""))
    squad_size = re.search(r"(\d+)-player", squad_sub)

    players = []
    for num, pos, pname, club, age, caps in ROW_RE.findall(raw):
        captain = bool(CAP_RE.search(pname))
        players.append(
            {
                "num": int(num),
                "name": clean(CAP_RE.sub("", pname)),
                "pos": pos,
                "club": clean(club),
                "age": int(age),
                "caps": int(caps),
                "captain": captain,
            }
        )

    return {
        "slug": slug,
        "name": clean(NAME_RE.search(raw).group(1)),
        "short": SHORT_NAMES.get(slug),
        "conf": CONF_RE.search(raw).group(1),
        "fifa_rank": int(RANK_RE.search(raw).group(1)),
        "coach": coach,
        "coach_since": coach_since,
        "group_result": group_result,
        "avg_age": float(avg_age_raw) if avg_age_raw else 0.0,
        "squad_size": int(squad_size.group(1)) if squad_size else len(players),
        "profile": f"teams/{slug}.html",
        "blurb": clean(SUB_RE.search(raw).group(1)),
        "players": players,
    }


def to_toml(team: dict) -> str:
    out = [f"[{team['slug']}]"]
    out.append(f"name        = {tstr(team['name'])}")
    if team.get("short"):
        out.append(f"short       = {tstr(team['short'])}")
    out.append(f"conf        = {tstr(team['conf'])}")
    out.append(f"fifa_rank   = {team['fifa_rank']}")
    out.append(f"coach       = {tstr(team['coach'])}")
    out.append(f"coach_since = {tstr(team['coach_since'])}")
    out.append(f"group_result= {tstr(team['group_result'])}")
    out.append(f"avg_age     = {team['avg_age']}")
    out.append(f"squad_size  = {team['squad_size']}")
    out.append(f"profile     = {tstr(team['profile'])}")
    out.append(f"blurb       = {tstr(team['blurb'])}")
    out.append(f"players = [")
    for p in team["players"]:
        cap = ", captain = true" if p["captain"] else ""
        out.append(
            f"  {{ num = {p['num']}, name = {tstr(p['name'])}, pos = {tstr(p['pos'])}, "
            f"club = {tstr(p['club'])}, age = {p['age']}, caps = {p['caps']}{cap} }},"
        )
    out.append("]")
    return "\n".join(out)


def main() -> None:
    teams = [extract(p) for p in sorted(TEAMS_DIR.glob("*.html"))]
    header = (
        "# Per-team comparable stats + squads, scaffolded from teams/*.html by\n"
        "# scripts/extract_teams.py. Hand-editable; build.py only reads this file.\n"
    )
    OUT.write_text(
        header + "\n" + "\n\n".join(to_toml(t) for t in teams) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT.relative_to(ROOT)} — {len(teams)} teams")
    for t in teams:
        print(f"  {t['slug']:14} #{t['fifa_rank']:<3} {t['conf']:9} "
              f"{len(t['players'])} players  ({t['coach']})")


if __name__ == "__main__":
    main()
