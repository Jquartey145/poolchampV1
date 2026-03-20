"""
test_data_loader.py
--------------------
Run from the project root with:
    python test_data_loader.py

Tests each data_loader function independently without needing
to run the Streamlit app. Mocks out st.* calls so nothing crashes.
"""

import sys
import json
import types
import pandas as pd

# ── Mock Streamlit ────────────────────────────────────────────────────────────

def _noop(*args, **kwargs): pass
def _noop_ctx(*args, **kwargs):
    import contextlib
    @contextlib.contextmanager
    def _ctx(): yield
    return _ctx()

class _SecretsMock(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

try:
    with open("firestore-key.json", "r") as f:
        _key_contents = f.read()
    _secrets = _SecretsMock({"textkey": _key_contents})
except FileNotFoundError:
    print("⚠️  firestore-key.json not found — Firestore tests will fail.")
    _secrets = _SecretsMock({})

st_mock = types.ModuleType("streamlit")
st_mock.cache_data    = lambda **kw: (lambda f: f)
st_mock.spinner       = _noop_ctx
st_mock.warning       = lambda msg, **kw: print(f"  ⚠️  {msg}")
st_mock.error         = lambda msg, **kw: print(f"  ❌  {msg}")
st_mock.write         = lambda msg, **kw: print(f"  ℹ️  {msg}")
st_mock.success       = lambda msg, **kw: print(f"  ✅  {msg}")
st_mock.info          = lambda msg, **kw: print(f"  ℹ️  {msg}")
st_mock.progress      = lambda *a, **kw: types.SimpleNamespace(progress=_noop, empty=_noop)
st_mock.session_state = {}
st_mock.secrets       = _secrets
sys.modules["streamlit"] = st_mock

nav_mock = types.ModuleType("navigation")
nav_mock.render_navigation = _noop
sys.modules["navigation"] = nav_mock

# ── Imports ───────────────────────────────────────────────────────────────────

import requests
from data_loader import (
    TOURNAMENT_YEAR,
    detect_round,
    _get_tournament_dates,
    _get_team_espn_ids,
    _get_regular_season_game_ids,
    _fetch_player_stats_for_game,
    fetch_tournament_game_ids,
    fetch_live_player_boxscore,
    _get_tournament_teams,
    load_tournament_data,
)

SEPARATOR = "─" * 60

def section(title):  print(f"\n{SEPARATOR}\n  {title}\n{SEPARATOR}")
def ok(msg):         print(f"  ✅  {msg}")
def fail(msg):       print(f"  ❌  {msg}")
def info(msg):       print(f"  ℹ️   {msg}")


# ── Test: detect_round ────────────────────────────────────────────────────────

def test_detect_round():
    section("TEST — detect_round()")
    cases = [
        ("NCAA Men's Basketball Tournament - First Round",   "Round 1"),
        ("NCAA Men's Basketball Tournament - Second Round",  "Round 2"),
        ("NCAA Men's Basketball Tournament - Sweet 16",      "Sweet 16"),
        ("NCAA Men's Basketball Tournament - Elite Eight",   "Elite 8"),
        ("NCAA Men's Basketball Tournament - Final Four",    "Final 4"),
        ("NCAA Men's Basketball Tournament - Championship",  "Championship"),
        ("NCAA Men's Basketball Tournament - First Four",    "First Four"),
        ("Some random string",                               "Unknown Round"),
        (None,                                               "Unknown Round"),
    ]
    passed = True
    for headline, expected in cases:
        result = detect_round(headline)
        if result == expected:
            ok(f'"{str(headline)[:55]}" → {result}')
        else:
            fail(f'"{headline}" → got "{result}", expected "{expected}"')
            passed = False
    return passed


# ── Test: tournament dates ────────────────────────────────────────────────────

def test_tournament_dates():
    section("TEST — _get_tournament_dates() for 2026")
    dates = _get_tournament_dates(2026)
    ok(f"Dates: {dates}")
    expected = ["20260317", "20260318", "20260319", "20260320", "20260321", "20260322"]
    if dates == expected:
        ok("Dates match expected 2026 tournament schedule")
        return True
    else:
        fail(f"Expected {expected}, got {dates}")
        return False


# ── Test: ESPN scoreboard raw ─────────────────────────────────────────────────

def test_espn_scoreboard_raw():
    section("TEST — Raw ESPN scoreboard endpoint (2026 tournament dates)")

    dates     = _get_tournament_dates(2026)
    all_teams = {}

    for date_str in dates:
        url = (
            "https://site.api.espn.com/apis/site/v2/sports/basketball"
            f"/mens-college-basketball/scoreboard"
            f"?groups=100&limit=200&dates={date_str}"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ❌ {date_str}: request failed — {e}")
            continue

        events = data.get("events", [])

        # Show season.type breakdown
        type_counts = {}
        for e in events:
            t = e.get("season", {}).get("type")
            type_counts[t] = type_counts.get(t, 0) + 1
        print(f"\n  {date_str}: {len(events)} total events | season.type: {type_counts}")

        # Both filter approaches
        strict     = [e for e in events if e.get("season", {}).get("type") in (3, "3")]
        note_based = [
            e for e in events
            if any(
                any(kw in n.get("headline", "") for kw in [
                    "NCAA", "Tournament", "First Round", "Second Round",
                    "Sweet", "Elite", "Final Four", "Championship", "First Four"
                ])
                for comp in e.get("competitions", [])
                for n in comp.get("notes", [])
            )
        ]
        print(f"    season.type==3 filter : {len(strict)} games")
        print(f"    notes headline filter : {len(note_based)} games")

        # Print raw structure of first event on first date with games
        if not all_teams and (strict or note_based):
            sample_events = strict or note_based
            e    = sample_events[0]
            comp = e.get("competitions", [{}])[0]
            comp0 = comp.get("competitors", [{}])[0]
            print(f"\n  --- RAW SAMPLE ({date_str}) ---")
            print(f"    event name:              {e.get('name')}")
            print(f"    season.type:             {e.get('season', {}).get('type')}")
            print(f"    comp.bracketRegion:      {comp.get('bracketRegion')}")
            print(f"    comp.tournamentId:       {comp.get('tournamentId')}")
            print(f"    comp.notes:              {comp.get('notes')}")
            print(f"    competitor.seed:         {comp0.get('seed')}")
            print(f"    competitor.curatedRank:  {comp0.get('curatedRank')}")
            print(f"    competitor.team keys:    {list(comp0.get('team', {}).keys())}")

        tournament_events = strict if strict else note_based
        for event in tournament_events:
            for comp in event.get("competitions", []):
                region = comp.get("bracketRegion", "")
                if not region:
                    for note in comp.get("notes", []):
                        for r in ["East", "West", "South", "Midwest"]:
                            if r in note.get("headline", ""):
                                region = r
                                break

                for competitor in comp.get("competitors", []):
                    team_name = competitor.get("team", {}).get("displayName", "")
                    if not team_name:
                        continue

                    raw_seed = competitor.get("seed")
                    if raw_seed is None:
                        raw_seed = competitor.get("curatedRank", {}).get("current")
                    try:
                        seed = int(raw_seed)
                        seed = seed if 1 <= seed <= 16 else None
                    except (TypeError, ValueError):
                        seed = None

                    if team_name not in all_teams:
                        all_teams[team_name] = {"seed": seed, "region": region or "Unknown"}
                    else:
                        if all_teams[team_name]["seed"] is None and seed is not None:
                            all_teams[team_name]["seed"] = seed
                        if all_teams[team_name]["region"] in ("", "Unknown", "First Four") \
                                and region not in ("", "Unknown", "First Four"):
                            all_teams[team_name]["region"] = region

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n  {'='*60}")
    print(f"  TOTAL UNIQUE TEAMS FOUND: {len(all_teams)}")
    print(f"  {'='*60}")

    missing_seeds   = {t for t, v in all_teams.items() if v["seed"] is None}
    missing_regions = {t for t, v in all_teams.items() if v["region"] in ("", "Unknown")}

    if missing_seeds:
        print(f"\n  ⚠️  {len(missing_seeds)} teams missing seeds:")
        for t in sorted(missing_seeds): print(f"    - {t}")
    else:
        print(f"\n  ✅ All teams have seeds")

    if missing_regions:
        print(f"\n  ⚠️  {len(missing_regions)} teams missing regions:")
        for t in sorted(missing_regions): print(f"    - {t}")
    else:
        print(f"\n  ✅ All teams have regions")

    print(f"\n  {'Seed':<6} {'Region':<12} {'Team'}")
    print(f"  {'-'*6} {'-'*12} {'-'*35}")
    for team, meta in sorted(all_teams.items(), key=lambda x: (x[1]["seed"] or 99, x[0])):
        print(f"  {str(meta['seed']):<6} {meta['region']:<12} {team}")

    passed = len(all_teams) >= 64 and len(missing_seeds) <= 4
    if passed:
        ok(f"Found {len(all_teams)} teams — looks good")
    else:
        fail(f"Only {len(all_teams)} teams found or too many missing seeds")
    return passed


# ── Test: ESPN team ID lookup ─────────────────────────────────────────────────

def test_espn_team_ids():
    section("TEST — _get_team_espn_ids() for sample 2026 tournament teams")

    # Will be updated once bracket is confirmed — using known perennials for now
    sample_teams = [
        "Duke Blue Devils",
        "Kansas Jayhawks",
        "Kentucky Wildcats",
        "Gonzaga Bulldogs",
        "Auburn Tigers",
        "Houston Cougars",
    ]

    id_map = _get_team_espn_ids(sample_teams)

    if not id_map:
        fail("No team IDs returned — check ESPN teams endpoint")
        return False

    for team in sample_teams:
        if team in id_map:
            ok(f"{team} → ESPN ID: {id_map[team]}")
        else:
            fail(f"{team} — NOT FOUND in ESPN teams endpoint")

    return len(id_map) == len(sample_teams)


# ── Test: regular season game IDs for a team ─────────────────────────────────

def test_regular_season_game_ids():
    section("TEST — _get_regular_season_game_ids() for a sample team")

    # Duke's ESPN ID is stable
    sample_id   = "150"
    sample_name = "Duke Blue Devils"
    info(f"Fetching 2026 regular season game IDs for {sample_name} (ESPN ID: {sample_id})")

    game_ids = _get_regular_season_game_ids(sample_id, TOURNAMENT_YEAR)

    if not game_ids:
        fail("No game IDs returned")
        return False

    ok(f"Found {len(game_ids)} regular season games")
    info(f"First 5 game IDs: {game_ids[:5]}")
    return len(game_ids) >= 20  # expect ~30 regular season games


# ── Test: player stats for a single game ─────────────────────────────────────

def test_player_stats_for_game(game_id: str):
    section(f"TEST — _fetch_player_stats_for_game(game_id={game_id})")

    if not game_id or game_id == "0":
        info("No game_id provided — skipping (set TEST_GAME_ID in __main__)")
        return True

    rows = _fetch_player_stats_for_game(game_id)

    if not rows:
        fail(f"No rows returned for game {game_id}")
        return False

    df = pd.DataFrame(rows)
    ok(f"{len(df)} player rows returned")
    info(f"Columns: {df.columns.tolist()}")

    top = df.sort_values("points", ascending=False).head(5)[
        ["athlete_display_name", "team_display_name", "points", "fg_made", "fg_att"]
    ]
    print("\n  Top 5 scorers:")
    print(top.to_string(index=False))
    return True


# ── Test: live tournament game IDs ────────────────────────────────────────────

def test_fetch_tournament_game_ids(date_str: str):
    section(f"TEST — fetch_tournament_game_ids('{date_str}')")

    game_ids = fetch_tournament_game_ids(date_str)

    if not game_ids:
        info(f"No tournament games found for {date_str} — expected before Mar 17")
        return True

    ok(f"Found {len(game_ids)} game IDs: {game_ids}")
    return True


# ── Test: live boxscore ───────────────────────────────────────────────────────

def test_fetch_live_boxscore(game_id: str):
    section(f"TEST — fetch_live_player_boxscore(game_id={game_id})")

    if not game_id or game_id == "0":
        info("No game_id provided — skipping (set TEST_GAME_ID in __main__)")
        return True

    player_df, headline = fetch_live_player_boxscore(game_id)
    if player_df is None or player_df.empty:
        fail(f"No player data for game {game_id}")
        return False

    ok(f"Headline : {headline}")
    ok(f"Round    : {detect_round(headline)}")
    ok(f"{len(player_df)} player rows")

    top = player_df.nlargest(5, "pts")[["athlete_display_name", "team_display_name", "pts"]]
    print("\n  Top 5 scorers:")
    print(top.to_string(index=False))
    return True


# ── Test: Firestore tournament teams ─────────────────────────────────────────

def test_get_tournament_teams():
    section("TEST — _get_tournament_teams() from Firestore")

    teams = _get_tournament_teams()

    if not teams:
        info(f"No teams in Firestore for {TOURNAMENT_YEAR} — run TournamentAdmin after Selection Sunday")
        return True

    ok(f"Found {len(teams)} teams")
    df = pd.DataFrame(teams)
    print(df.sort_values(["seed", "team_name"])[["seed", "team_name", "region"]].to_string(index=False))

    issues = [
        t for t in teams
        if not t.get("team_name") or t.get("seed") is None or not t.get("region")
    ]
    if issues:
        for t in issues:
            fail(f"Incomplete record: {t}")
        return False

    ok("All teams have name, seed, and region")
    return True


# ── Test: Firestore tournament data ──────────────────────────────────────────

def test_load_tournament_data():
    section("TEST — load_tournament_data() from Firestore")

    df = load_tournament_data()

    if df is None or df.empty:
        info("No tournament data yet — expected before Round 1 starts")
        return True

    ok(f"{len(df)} player records loaded")
    if "total_points" in df.columns:
        top = df.nlargest(10, "total_points")[["Player", "Team", "total_points"]]
        print("\n  Top 10 tournament scorers:")
        print(top.to_string(index=False))
    return True


# ── Test: regular season stats endpoint (ESPN roster) ────────────────────────

def test_regular_season_stats_espn():
    section("TEST — Regular season stats via ESPN roster endpoint")

    SAMPLE_TEAMS = [
        {"name": "Duke Blue Devils",  "espn_id": "150"},
        {"name": "Auburn Tigers",     "espn_id": "2"},
        {"name": "Houston Cougars",   "espn_id": "248"},
        {"name": "Florida Gators",    "espn_id": "57"},
    ]

    all_players = []

    for team in SAMPLE_TEAMS:
        url = (
            f"https://site.web.api.espn.com/apis/site/v2/sports/basketball"
            f"/mens-college-basketball/teams/{team['espn_id']}/roster"
            f"?region=us&lang=en&contentorigin=espn&season={TOURNAMENT_YEAR}&seasontype=2"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            fail(f"{team['name']}: {e}")
            continue

        athletes = data.get("athletes", [])
        print(f"\n  {team['name']}: {len(athletes)} athletes")

        if athletes:
            a = athletes[0]
            print(f"    First athlete keys : {list(a.keys())}")
            stats = a.get("statistics", a.get("stats", {}))
            print(f"    Stats type         : {type(stats)}")
            if isinstance(stats, dict):
                print(f"    Stats keys         : {list(stats.keys())}")

        for athlete in athletes:
            name  = athlete.get("displayName", athlete.get("fullName", ""))
            stats = athlete.get("statistics", {})

            stat_map = {}
            if isinstance(stats, dict):
                for cat in stats.get("splits", {}).get("categories", []):
                    for s in cat.get("stats", []):
                        stat_map[s.get("name", "")] = s.get("value", 0)
            elif isinstance(stats, list):
                stat_map = {s.get("name"): s.get("value") for s in stats}

            all_players.append({
                "name": name,
                "team": team["name"],
                "ppg":  stat_map.get("avgPoints", stat_map.get("points", 0)),
                "gp":   stat_map.get("gamesPlayed", 0),
                "fgp":  stat_map.get("fieldGoalPct", 0),
                "stat_keys": list(stat_map.keys())[:8],
            })

    players_with_stats = [p for p in all_players if p["ppg"] and float(p["ppg"]) > 0]
    print(f"\n  Total players: {len(all_players)}")
    print(f"  With PPG > 0 : {len(players_with_stats)}")

    if all_players:
        print(f"  Sample stat keys: {all_players[0]['stat_keys']}")

    if players_with_stats:
        top = sorted(players_with_stats, key=lambda x: float(x["ppg"]), reverse=True)[:10]
        print(f"\n  {'Name':<25} {'Team':<25} {'GP':<5} {'PPG':<6} {'FG%'}")
        print(f"  {'-'*25} {'-'*25} {'-'*5} {'-'*6} {'-'*5}")
        for p in top:
            print(f"  {p['name']:<25} {p['team']:<25} {str(p['gp']):<5} {str(p['ppg']):<6} {p['fgp']}")
        return True
    else:
        fail("No players with stats found — endpoint may need different parsing")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🏀 data_loader.py Test Suite")
    print(f"   TOURNAMENT_YEAR = {TOURNAMENT_YEAR}")
    print(f"   Today is March 15 2026 — bracket just announced, games start March 17")

    # First Four: March 17-18
    # Round 1:    March 19-20
    # Round 2:    March 21-22
    TEST_DATE    = "2026-03-19"   # Round 1 Day 1 — update as tournament progresses
    TEST_GAME_ID = "401856491"            # Replace with a real game ID from test_fetch_tournament_game_ids

    results = {}
    # results["detect_round"]            = test_detect_round()
    # results["tournament_dates"]        = test_tournament_dates()
    # results["espn_scoreboard_raw"]     = test_espn_scoreboard_raw()
    # results["espn_team_ids"]           = test_espn_team_ids()
    # results["regular_season_game_ids"] = test_regular_season_game_ids()
    # results["regular_season_stats"]    = test_regular_season_stats_espn()
    # results["tournament_game_ids"]     = test_fetch_tournament_game_ids(TEST_DATE)
    # results["player_stats_for_game"]   = test_player_stats_for_game(TEST_GAME_ID)
    results["live_boxscore"]           = test_fetch_live_boxscore(TEST_GAME_ID)
    # results["firestore_teams"]         = test_get_tournament_teams()
    # results["firestore_tournament"]    = test_load_tournament_data()

    print(f"\n{SEPARATOR}")
    print("  SUMMARY")
    print(SEPARATOR)
    for name, passed in results.items():
        print(f"  {'✅ PASS' if passed else '❌ FAIL'}  {name}")

    failed = [k for k, v in results.items() if not v]
    if not failed:
        print("\n  🎉 All tests passed!")
    else:
        print(f"\n  ⚠️  {len(failed)} test(s) need attention: {', '.join(failed)}")