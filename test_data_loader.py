"""
test_data_loader.py
--------------------
Run from the project root with:
    python test_data_loader.py

Tests each data_loader function independently without needing
to run the Streamlit app. Mocks out st.* calls so nothing crashes.

Requirements:
    - firestore-key.json in the same directory
    - pip install sportsdataverse pandas firebase-admin
"""

import sys
import json
import types
import pandas as pd

# ── Mock Streamlit so imports don't crash ─────────────────────────────────────

def _noop(*args, **kwargs): pass
def _noop_ctx(*args, **kwargs):
    import contextlib
    @contextlib.contextmanager
    def _ctx(): yield
    return _ctx()

# st.secrets mock — reads firestore-key.json so firebase_util.py initialises correctly
class _SecretsMock(dict):
    """Behaves like st.secrets: supports both .get() and attribute access."""
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
st_mock.cache_data    = lambda **kw: (lambda f: f)   # passthrough decorator
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

# Also mock navigation so data_loader doesn't pull in Streamlit pages
nav_mock = types.ModuleType("navigation")
nav_mock.render_navigation = _noop
sys.modules["navigation"] = nav_mock

# ── Now safe to import ────────────────────────────────────────────────────────

import sportsdataverse.mbb as mbb
from data_loader import (
    TOURNAMENT_YEAR,
    detect_round,
    _get_tournament_teams,
    fetch_tournament_game_ids,
    fetch_live_player_boxscore,
    load_regular_season_data,
    load_tournament_data,
)

SEPARATOR = "─" * 60


def section(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def ok(msg: str):
    print(f"  ✅  {msg}")


def fail(msg: str):
    print(f"  ❌  {msg}")


def info(msg: str):
    print(f"  ℹ️   {msg}")


# ── Test 1: detect_round ──────────────────────────────────────────────────────

def test_available_mbb_functions():
    section("TEST 0 — Available sportsdataverse.mbb functions")
    all_fns = [x for x in dir(mbb) if not x.startswith("_")]
    ok(f"{len(all_fns)} public functions/attributes found")
    print()
    for fn in sorted(all_fns):
        print(f"    {fn}")
    return True

def test_detect_round():
    section("TEST 1 — detect_round()")

    cases = [
        ("NCAA Men's Basketball Tournament - East Regional - First Round",  "Round 1"),
        ("NCAA Men's Basketball Tournament - Second Round",                  "Round 2"),
        ("NCAA Men's Basketball Tournament - Sweet 16",                     "Sweet 16"),
        ("NCAA Men's Basketball Tournament - Elite Eight",                   "Elite 8"),
        ("NCAA Men's Basketball Tournament - Final Four",                    "Final 4"),
        ("NCAA Men's Basketball Tournament - National Championship",         "Championship"),
        ("NCAA Men's Basketball Tournament - First Four",                    "First Four"),
        ("Some random string",                                               "Unknown Round"),
        (None,                                                               "Unknown Round"),
    ]

    all_passed = True
    for headline, expected in cases:
        result = detect_round(headline)
        if result == expected:
            ok(f'"{str(headline)[:50]}..." → {result}')
        else:
            fail(f'"{headline}" → got "{result}", expected "{expected}"')
            all_passed = False

    return all_passed


# ── Test 2: Tournament teams from Firestore ───────────────────────────────────

def test_get_tournament_teams():
    section("TEST 2 — _get_tournament_teams() from Firestore")

    teams = _get_tournament_teams()

    if not teams:
        info(
            f"No teams found in Firestore for {TOURNAMENT_YEAR}. "
            "This is expected before Selection Sunday — run TournamentAdmin first."
        )
        return True  # Not a failure, just not populated yet

    ok(f"Found {len(teams)} teams in Firestore")

    df = pd.DataFrame(teams)
    print(df.sort_values(["seed", "team_name"])[["seed", "team_name", "region"]].to_string(index=False))

    # Validate structure
    issues = []
    for t in teams:
        if not t.get("team_name"):
            issues.append(f"Missing team_name: {t}")
        if t.get("seed") is None:
            issues.append(f"Missing seed for {t.get('team_name')}")
        if not t.get("region"):
            issues.append(f"Missing region for {t.get('team_name')}")

    if issues:
        for issue in issues:
            fail(issue)
        return False

    ok("All teams have name, seed, and region")
    return True


# ── Test 3: Live schedule / game IDs ─────────────────────────────────────────

def test_fetch_game_ids(date_str: str):
    section(f"TEST 3 — fetch_tournament_game_ids('{date_str}')")

    game_ids = fetch_tournament_game_ids(date_str)

    if not game_ids:
        info(
            f"No tournament games found for {date_str}. "
            "This is expected if the date is before the tournament or games haven't started."
        )
        return True

    ok(f"Found {len(game_ids)} game IDs: {game_ids}")
    return True


# ── Test 4: Live player boxscore for a single game ───────────────────────────

def test_fetch_player_boxscore(game_id: int):
    section(f"TEST 4 — fetch_live_player_boxscore(game_id={game_id})")

    player_df, headline = fetch_live_player_boxscore(game_id)

    if player_df is None or player_df.empty:
        fail(f"No player data returned for game {game_id}")
        return False

    ok(f"Headline: {headline}")
    ok(f"Round detected: {detect_round(headline)}")
    ok(f"{len(player_df)} player rows, {len(player_df.columns)} columns")

    # Dump ALL columns so we can confirm exact names
    print("\n  ALL COLUMNS:")
    for col in sorted(player_df.columns.tolist()):
        sample = player_df[col].iloc[0] if len(player_df) > 0 else "n/a"
        print(f"    {col:<45} sample: {str(sample)[:60]}")

    # Try common points column names
    pts_col = next((c for c in ["pts", "points", "PTS", "Points", "statistics_pts"] if c in player_df.columns), None)
    name_col = next((c for c in ["athlete_display_name", "athlete_name", "name", "display_name"] if c in player_df.columns), None)
    team_col = next((c for c in ["team_display_name", "team_name", "team", "Team"] if c in player_df.columns), None)

    print(f"\n  Points column found: {pts_col}")
    print(f"  Name column found:   {name_col}")
    print(f"  Team column found:   {team_col}")

    if pts_col and name_col:
        player_df[pts_col] = pd.to_numeric(player_df[pts_col], errors="coerce").fillna(0)
        cols = [c for c in [name_col, team_col, pts_col] if c]
        top = player_df.nlargest(5, pts_col)[cols]
        print("\n  Top scorers:")
        print(top.to_string(index=False))

    return True


# ── Test 5: Raw sportsdataverse schedule (inspect columns) ───────────────────

def test_espn_schedule(date_str: str):
    section(f"TEST 5 — mbb.espn_mbb_schedule(dates={date_str}, season_type=3)")
    info("Inspecting raw schedule columns and sample data...")

    try:
        date_int = int(date_str.replace("-", ""))
        df = mbb.espn_mbb_schedule(dates=date_int, season_type=3, return_as_pandas=True)
    except Exception as e:
        fail(f"espn_mbb_schedule raised: {e}")
        return False

    if df is None or df.empty:
        info("No data returned — tournament may not have started yet for this date.")
        return True

    ok(f"{len(df)} games returned")
    info(f"Columns: {df.columns.tolist()}")

    # Check for seed columns specifically
    for col in ["home_seed", "away_seed", "home_display_name", "away_display_name", "notes_headline"]:
        if col in df.columns:
            ok(f"Column '{col}' is present ✓")
        else:
            fail(f"Column '{col}' is MISSING — may affect team/seed loading")

    print("\n  Sample row:")
    print(df.iloc[0].to_string())
    return True


# ── Test 6: Regular season data load ─────────────────────────────────────────

def test_seed_extraction(date_str: str):
    """
    TEST 6 — Validate that seeds can be extracted from espn_mbb_schedule
    using home_current_rank/away_current_rank during tournament dates.
    Does NOT require Firestore.
    """
    section(f"TEST 6 — Seed extraction from schedule (date={date_str})")

    try:
        date_int = int(date_str.replace("-", ""))
        df = mbb.espn_mbb_schedule(dates=date_int, season_type=3, return_as_pandas=True)
    except Exception as e:
        fail(f"Schedule fetch failed: {e}")
        return False

    if df is None or df.empty:
        info("No schedule data — tournament not started yet for this date.")
        return True

    def _safe_int(val):
        try:
            v = int(val)
            return v if 1 <= v <= 16 else None
        except (ValueError, TypeError):
            return None

    seed_col = "home_seed" if "home_seed" in df.columns else "home_current_rank"
    info(f"Using '{seed_col}' as seed source")

    extracted = []
    for _, row in df.iterrows():
        home = row.get("home_display_name", "")
        away = row.get("away_display_name", "")
        home_seed = _safe_int(row.get(seed_col))
        away_seed = _safe_int(row.get("away_seed" if "away_seed" in df.columns else "away_current_rank"))
        headline = row.get("notes_headline", "")

        region = "First Four"
        for r in ["East", "West", "South", "Midwest"]:
            if r in str(headline):
                region = r
                break

        extracted.append({"team": home, "seed": home_seed, "region": region})
        extracted.append({"team": away, "seed": away_seed, "region": region})

    result_df = pd.DataFrame(extracted).drop_duplicates("team").sort_values(["seed", "team"])
    seeds_found = result_df["seed"].notna().sum()
    seeds_missing = result_df["seed"].isna().sum()

    ok(f"{len(result_df)} unique teams found")
    if seeds_missing == 0:
        ok(f"All {seeds_found} teams have seeds ✓")
    else:
        fail(f"{seeds_missing} teams missing seeds — may need manual entry")

    print(f"\n  {'Seed':<6} {'Team':<40} {'Region'}")
    print(f"  {'-'*6} {'-'*40} {'-'*10}")
    for _, r in result_df.iterrows():
        print(f"  {str(r['seed']):<6} {r['team']:<40} {r['region']}")

    return seeds_missing == 0


def test_load_regular_season(sample_teams: list = None):
    section("TEST 7 — load_mbb_player_boxscore() — raw parquet (no Firestore needed)")
    info("Loading 2025 season parquet directly — may take 30-60s first time...")

    # Use a hardcoded sample of 2025 tournament teams if none provided
    if not sample_teams:
        sample_teams = [
            {"team_name": "Houston Cougars",   "seed": 1,  "region": "Midwest"},
            {"team_name": "Duke Blue Devils",  "seed": 1,  "region": "East"},
            {"team_name": "Auburn Tigers",     "seed": 1,  "region": "South"},
            {"team_name": "Florida Gators",    "seed": 1,  "region": "West"},
            {"team_name": "Alabama Crimson Tide", "seed": 2, "region": "South"},
            {"team_name": "Michigan State Spartans", "seed": 2, "region": "East"},
        ]

    try:
        box_df = mbb.load_mbb_player_boxscore(seasons=[2025], return_as_pandas=True)
    except Exception as e:
        fail(f"load_mbb_player_boxscore raised: {e}")
        return False

    if box_df is None or box_df.empty:
        fail("No data returned from parquet loader")
        return False

    ok(f"Raw parquet: {len(box_df)} rows, {len(box_df.columns)} columns")
    info(f"Columns sample: {box_df.columns[:10].tolist()}")

    team_names = {t["team_name"] for t in sample_teams}
    reg_df = box_df[(box_df["season_type"] == 2) & (box_df["team_display_name"].isin(team_names))]

    ok(f"Regular season rows for sample teams: {len(reg_df)}")

    if reg_df.empty:
        fail("No rows matched sample teams — check team name spelling vs ESPN")
        actual_names = box_df["team_display_name"].dropna().unique()
        info(f"Sample of actual team names in parquet: {sorted(actual_names)[:20]}")
        return False

    # Show top scorers
    reg_df = reg_df.copy()
    pts_col = "pts" if "pts" in reg_df.columns else "points"
    reg_df[pts_col] = pd.to_numeric(reg_df[pts_col], errors="coerce").fillna(0)
    top = (
        reg_df.groupby(["athlete_display_name", "team_display_name"])[pts_col]
        .sum()
        .reset_index()
        .nlargest(10, "points")
    )
    print("\n  Top 10 scorers (sample teams, regular season):")
    print(top.to_string(index=False))
    return True


# ── Test 7: Tournament data from Firestore ────────────────────────────────────

def test_load_tournament_data():
    section("TEST 7 — load_tournament_data() from Firestore")

    df = load_tournament_data()

    if df is None or df.empty:
        info(
            "No tournament data in Firestore yet. "
            "This is expected before the tournament starts."
        )
        return True

    ok(f"{len(df)} player tournament records loaded")

    if "total_points" in df.columns:
        top = df.nlargest(10, "total_points")[["Player", "Team", "total_points"]]
        print("\n  Top 10 tournament scorers so far:")
        print(top.to_string(index=False))

    return True


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n🏀 data_loader.py Test Suite")
    print(f"   TOURNAMENT_YEAR = {TOURNAMENT_YEAR}")

    # ── Configure test parameters ─────────────────────────────────────────────
    # Set a known tournament game date to test live schedule/boxscore fetching.
    # Use a past tournament date that definitely has games:
    TEST_DATE = "2025-03-20"   # ← Round 1 Day 1, change as needed

    # Set a known game ID from a past tournament game for boxscore testing.
    # Find one from ESPN or by running test_fetch_game_ids first.
    TEST_GAME_ID = 401745972   # ← replace with a real game_id from test 3

    results = {}

    # Dump available mbb functions first
    results["mbb_functions"]       = test_available_mbb_functions()

    # Always-safe tests (no network needed)
    results["detect_round"]         = test_detect_round()

    # Firestore tests (expected to be empty before tournament)
    results["tournament_teams"]     = test_get_tournament_teams()
    results["tournament_data"]      = test_load_tournament_data()

    # Live ESPN schedule tests
    results["espn_schedule"]        = test_espn_schedule(TEST_DATE)
    results["game_ids"]             = test_fetch_game_ids(TEST_DATE)

    # Seed extraction from schedule (no Firestore needed)
    results["seed_extraction"]      = test_seed_extraction(TEST_DATE)

    # Live player boxscore — use a game_id from TEST 3 output above
    results["player_boxscore"]      = test_fetch_player_boxscore(TEST_GAME_ID)

    # Regular season parquet load — uses hardcoded sample teams, no Firestore needed
    results["regular_season"]       = test_load_regular_season()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{SEPARATOR}")
    print("  SUMMARY")
    print(SEPARATOR)
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")

    failed = [k for k, v in results.items() if not v]
    if not failed:
        print("\n  🎉 All tests passed!")
    else:
        print(f"\n  ⚠️  {len(failed)} test(s) need attention: {', '.join(failed)}")