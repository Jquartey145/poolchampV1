import streamlit as st
import pandas as pd
import datetime
import time
import requests
from firebase_util import (
    tournament_data_exists,
    get_tournament_data_from_firestore,
    save_player_data,
    get_regular_season_data,
    save_regular_season_data,
    update_submission_totals,
    db
)

TOURNAMENT_YEAR = 2026

ESPN_SCOREBOARD = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/scoreboard"
    "?groups=100&limit=200&dates={date}"
)
ESPN_SUMMARY = (
    "https://site.web.api.espn.com/apis/site/v2/sports/basketball"
    "/mens-college-basketball/summary?event={game_id}"
)

# ── Round name detection ──────────────────────────────────────────────────────

ROUND_KEYWORDS = {
    "First Four":            "First Four",
    "1st Round":             "Round 1",      # ← gameNote format
    "First Round":           "Round 1",
    "2nd Round":             "Round 2",      # ← gameNote format
    "Second Round":          "Round 2",
    "Sweet 16":              "Sweet 16",
    "Sweet Sixteen":         "Sweet 16",
    "Elite Eight":           "Elite 8",
    "Elite 8":               "Elite 8",
    "Final Four":            "Final 4",
    "National Championship": "Championship",
    "Championship":          "Championship",
}

def detect_round(headline: str) -> str:
    if not isinstance(headline, str):
        return "Unknown Round"
    for keyword, round_name in ROUND_KEYWORDS.items():
        if keyword.lower() in headline.lower():
            return round_name
    return "Unknown Round"


# ── ESPN helpers ──────────────────────────────────────────────────────────────

def _espn_get(url: str) -> dict:
    """GET an ESPN endpoint, return parsed JSON or {}."""
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.warning(f"ESPN request failed: {url}\n{e}")
        return {}


# ── Firestore helpers ─────────────────────────────────────────────────────────

def safe_batch_commit(batch, max_retries=3):
    for attempt in range(max_retries):
        try:
            batch.commit()
            return
        except Exception as e:
            if attempt == max_retries - 1:
                st.error(f"Failed to commit batch after {max_retries} attempts: {str(e)}")
                raise
            time.sleep(2 ** attempt)


def _get_tournament_teams() -> list:
    docs = (
        db.collection("tournament_teams")
        .document(str(TOURNAMENT_YEAR))
        .collection("teams")
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def save_tournament_teams(teams: list):
    year_str = str(TOURNAMENT_YEAR)
    col_ref = (
        db.collection("tournament_teams")
        .document(year_str)
        .collection("teams")
    )
    batch = db.batch()
    for team in teams:
        doc_ref = col_ref.document(team["team_name"].replace(" ", "_"))
        batch.set(doc_ref, team)
    batch.commit()


# ── Tournament dates ──────────────────────────────────────────────────────────

def _get_tournament_dates(year: int) -> list:
    """
    Return YYYYMMDD strings covering First Four through Round 2.
    Hardcoded for 2026; falls back to dynamic calculation for other years.
    2026: Selection Sunday Mar 15, First Four Mar 17-18, Rounds 1-2 Mar 19-22.
    """
    if year == 2026:
        return ["20260317", "20260318", "20260319", "20260320", "20260321", "20260322"]

    # Dynamic fallback: second Sunday of March + offsets
    d = datetime.date(year, 3, 1)
    sundays = [
        day for day in (d + datetime.timedelta(n) for n in range(31))
        if day.weekday() == 6
    ]
    selection_sunday = sundays[1]
    return [
        (selection_sunday + datetime.timedelta(days=offset)).strftime("%Y%m%d")
        for offset in [2, 3, 4, 5, 6, 7]
    ]


# ── Regular season data via ESPN ──────────────────────────────────────────────

def _get_team_espn_ids(team_names: list, id_overrides: dict = None) -> dict:
    """
    Map display names → ESPN team IDs using the ESPN teams endpoint.
    id_overrides: {team_name: espn_id} — skips the lookup for teams where
    the ID is already known (e.g. small programs missing from the bulk list).
    Returns {display_name: espn_id}
    """
    id_overrides = id_overrides or {}

    # Start with any known overrides
    id_map = {name: eid for name, eid in id_overrides.items() if name in team_names}

    # Only look up teams not already resolved
    remaining = [t for t in team_names if t not in id_map]
    if not remaining:
        return id_map

    url = (
        "https://site.api.espn.com/apis/site/v2/sports/basketball"
        "/mens-college-basketball/teams?limit=500"
    )
    data = _espn_get(url)
    for item in (
        data.get("sports", [{}])[0]
            .get("leagues", [{}])[0]
            .get("teams", [])
    ):
        team    = item.get("team", {})
        display = team.get("displayName", "")
        if display in remaining:
            id_map[display] = team.get("id", "")

    return id_map


def _get_regular_season_game_ids(team_espn_id: str, year: int) -> list:
    """Fetch all regular season game IDs for a team."""
    url = (
        f"https://site.api.espn.com/apis/site/v2/sports/basketball"
        f"/mens-college-basketball/teams/{team_espn_id}/schedule?season={year}"
    )
    data = _espn_get(url)
    game_ids = []
    for event in data.get("events", []):
        season_type = event.get("seasonType", {})
        # ESPN returns seasonType.id as int or string depending on the program
        type_id   = str(season_type.get("id", "")).strip()
        type_name = season_type.get("name", "").lower()
        if type_id == "2" or type_name == "regular season":
            game_ids.append(event["id"])
    if not game_ids:
        seen_types = list({
            f"id={e.get('seasonType',{}).get('id')} name={e.get('seasonType',{}).get('name')}"
            for e in data.get("events", [])
        })
        st.warning(
            f"No regular season games found for ESPN ID {team_espn_id}. "
            f"Season types seen: {seen_types}. "
            f"Total events: {len(data.get('events', []))}"
        )
    return game_ids


def _fetch_player_stats_for_game(game_id: str) -> list:
    """
    Fetch player stats from ESPN summary endpoint for a single game.
    Returns list of dicts with per-player stats.
    """
    url = ESPN_SUMMARY.format(game_id=game_id)
    data = _espn_get(url)
    rows = []

    for team_block in data.get("boxscore", {}).get("players", []):
        team_name = team_block.get("team", {}).get("displayName", "")
        for stat_group in team_block.get("statistics", []):
            labels = stat_group.get("labels", [])
            for athlete_entry in stat_group.get("athletes", []):
                athlete = athlete_entry.get("athlete", {})
                stats   = athlete_entry.get("stats", [])
                stat_map = dict(zip(labels, stats))

                def _split(s):
                    parts = str(s).split("-")
                    try:
                        return int(parts[0]), int(parts[1])
                    except Exception:
                        return 0, 0

                fg_made,  fg_att  = _split(stat_map.get("FG",  "0-0"))
                fg3_made, fg3_att = _split(stat_map.get("3PT", "0-0"))

                try:
                    pts = int(float(stat_map.get("PTS", 0) or 0))
                except (ValueError, TypeError):
                    pts = 0

                rows.append({
                    "athlete_display_name": athlete.get("displayName", ""),
                    "team_display_name":    team_name,
                    "points":   pts,
                    "fg_made":  fg_made,
                    "fg_att":   fg_att,
                    "fg3_made": fg3_made,
                    "fg3_att":  fg3_att,
                    "position": athlete.get("position", {}).get("abbreviation", ""),
                })
    return rows


def build_regular_season_data(tournament_teams: list) -> pd.DataFrame:
    """
    Load regular season stats for all tournament teams using the ESPN summary endpoint.
    Called by load_regular_season_data() and by TournamentAdmin after saving teams.
    """
    team_meta = {
        t["team_name"]: {"seed": t["seed"], "region": t.get("region", "N/A")}
        for t in tournament_teams
        if t.get("seed") is not None and int(t["seed"]) <= 16
    }
    team_names = list(team_meta.keys())

    if not team_names:
        st.warning("No valid tournament teams found.")
        return pd.DataFrame()

    st.write(f"Resolving ESPN IDs for {len(team_names)} teams...")

    # Build override map from any teams that have an espn_id stored directly
    id_overrides = {
        t["team_name"]: t["espn_id"]
        for t in tournament_teams
        if t.get("espn_id") and t["team_name"] in team_names
    }
    if id_overrides:
        st.write(f"  Using {len(id_overrides)} direct ESPN ID override(s): {list(id_overrides.keys())}")

    id_map = _get_team_espn_ids(team_names, id_overrides)

    missing = [t for t in team_names if t not in id_map]
    if missing:
        st.warning(f"Could not find ESPN IDs for: {missing}")

    all_rows = []
    progress  = st.progress(0)
    teams_done = 0

    for team_name, espn_id in id_map.items():
        st.write(f"  Fetching schedule for {team_name} (ID: {espn_id})...")
        game_ids = _get_regular_season_game_ids(espn_id, TOURNAMENT_YEAR)
        st.write(f"    {len(game_ids)} regular season games found")

        for game_id in game_ids:
            rows = _fetch_player_stats_for_game(game_id)
            all_rows.extend(r for r in rows if r["team_display_name"] == team_name)

        teams_done += 1
        progress.progress(teams_done / len(id_map))

    progress.empty()

    if not all_rows:
        st.warning("No player rows fetched from ESPN summary endpoint.")
        return pd.DataFrame()

    raw = pd.DataFrame(all_rows)

    player_stats = (
        raw.groupby(["athlete_display_name", "team_display_name"])
        .agg(
            Games    =("points",   "count"),
            Points   =("points",   "sum"),
            FG_made  =("fg_made",  "sum"),
            FG_att   =("fg_att",   "sum"),
            FG3_made =("fg3_made", "sum"),
            FG3_att  =("fg3_att",  "sum"),
        )
        .reset_index()
    )

    player_stats["PPG"] = (player_stats["Points"] / player_stats["Games"]).round(1)
    player_stats["FG%"] = (
        (player_stats["FG_made"] / player_stats["FG_att"].replace(0, float("nan"))) * 100
    ).round(1).fillna(0.0)
    player_stats["3P%"] = (
        (player_stats["FG3_made"] / player_stats["FG3_att"].replace(0, float("nan"))) * 100
    ).round(1).fillna(0.0)

    player_stats = player_stats[player_stats["Games"] >= 5]

    player_stats["Seed"]   = player_stats["team_display_name"].map(
        lambda t: team_meta.get(t, {}).get("seed", "N/A")
    )
    player_stats["Region"] = player_stats["team_display_name"].map(
        lambda t: team_meta.get(t, {}).get("region", "N/A")
    )

    positions = (
        raw.groupby(["athlete_display_name", "team_display_name"])["position"]
        .agg(lambda x: x.mode()[0] if not x.mode().empty else "")
        .reset_index()
        .rename(columns={"position": "Position"})
    )
    player_stats = player_stats.merge(
        positions, on=["athlete_display_name", "team_display_name"], how="left"
    )

    player_stats = player_stats.rename(columns={
        "athlete_display_name": "Player",
        "team_display_name":    "Team",
    })

    return player_stats[[
        "Player", "Team", "Seed", "Region", "Position",
        "Games", "Points", "PPG", "FG%", "3P%"
    ]].sort_values("Points", ascending=False)


@st.cache_data(ttl=3600)
def load_regular_season_data() -> pd.DataFrame:
    """
    Load regular season player stats for all tournament teams.
    Checks Firestore cache first; falls back to ESPN API if not cached.
    """
    year_str = str(TOURNAMENT_YEAR)

    players = get_regular_season_data(year_str)
    if players:
        return pd.DataFrame(players)

    tournament_teams = _get_tournament_teams()
    if not tournament_teams:
        st.warning("No tournament teams found. Please use the Tournament Admin page first.")
        return pd.DataFrame()

    with st.spinner("Loading regular season player data from ESPN..."):
        final_df = build_regular_season_data(tournament_teams)

    if final_df.empty:
        return pd.DataFrame()

    save_regular_season_data(year_str, final_df.to_dict(orient="records"))
    return final_df


# ── Tournament game updates (live) ────────────────────────────────────────────

def fetch_tournament_game_ids(date_str: str) -> list:
    """
    Get all tournament game IDs for a given date.
    date_str: "YYYY-MM-DD"
    """
    date_compact = date_str.replace("-", "")
    url  = ESPN_SCOREBOARD.format(date=date_compact)
    data = _espn_get(url)

    # Try season type 3 first
    game_ids = [
        e["id"] for e in data.get("events", [])
        if e.get("season", {}).get("type") in (3, "3")
    ]

    # Fallback: check notes headlines for tournament language
    if not game_ids:
        for event in data.get("events", []):
            for comp in event.get("competitions", []):
                for note in comp.get("notes", []):
                    if any(kw in note.get("headline", "") for kw in [
                        "Tournament", "NCAA", "First Round", "Second Round",
                        "Sweet", "Elite", "Final Four", "Championship", "First Four"
                    ]):
                        game_ids.append(event["id"])
                        break

    return list(dict.fromkeys(game_ids))  # deduplicate, preserve order


def fetch_live_player_boxscore(game_id: str) -> tuple:
    url  = ESPN_SUMMARY.format(game_id=game_id)
    data = _espn_get(url)

    headline = ""
    try:
        header = data.get("header", {})
        comps  = header.get("competitions", [{}])

        # Primary: gameNote (most reliable — e.g. "NCAA ... - South Region - 1st Round")
        headline = header.get("gameNote", "")

        if not headline and comps:
            comp  = comps[0]
            notes = comp.get("notes", [{}])
            if notes:
                headline = notes[0].get("headline", "")

    except Exception:
        pass

    rows = _fetch_player_stats_for_game(game_id)
    if not rows:
        return pd.DataFrame(), headline

    player_df = pd.DataFrame(rows).rename(columns={"points": "pts"})
    return player_df, headline


def update_daily_player_points(date_str: str):
    """
    Fetch live tournament game data for a given date and update Firestore.
    date_str: "YYYY-MM-DD"
    """
    st.write(f"🚀 Starting live player points update for {date_str}")
    year_str = str(TOURNAMENT_YEAR)

    with st.spinner("Fetching today's tournament games from ESPN..."):
        game_ids = fetch_tournament_game_ids(date_str)

    if not game_ids:
        st.warning(f"⚠️ No tournament games found for {date_str}.")
        return

    st.write(f"🏀 Found {len(game_ids)} tournament game(s)")

    tournament_ref = db.collection("tournament_data").document(year_str)
    players_ref    = tournament_ref.collection("players")

    batch       = db.batch()
    batch_count = 0
    MAX_BATCH   = 400
    last_round  = "Unknown Round"

    for game_id in game_ids:
        st.write(f"🔍 Fetching boxscore for game {game_id}...")
        player_df, headline = fetch_live_player_boxscore(game_id)

        if player_df is None or player_df.empty:
            st.warning(f"⚠️ No player data for game {game_id}")
            continue

        round_name = detect_round(headline)
        if round_name != "Unknown Round":
            last_round = round_name
        game_title = headline or f"Game {game_id}"
        st.write(f"  📋 {game_title} → {round_name}")

        player_df["pts"] = pd.to_numeric(player_df["pts"], errors="coerce").fillna(0)

        for _, row in player_df.iterrows():
            player_name = row.get("athlete_display_name", "")
            team_name   = row.get("team_display_name", "")
            points      = int(row.get("pts", 0))
            if not player_name:
                continue

            existing = list(
                players_ref
                .where("Player", "==", player_name)
                .where("Team",   "==", team_name)
                .limit(1)
                .stream()
            )

            if existing:
                doc_ref = players_ref.document(existing[0].id)
                current = existing[0].to_dict()
                rp      = current.get("round_points", {})
                rp[round_name] = rp.get(round_name, 0) + points
                games   = current.get("games", [])
                games.append({
                    "game_id":   str(game_id),
                    "date":      date_str,
                    "round":     round_name,
                    "points":    points,
                    "game_title": game_title,
                })
                batch.update(doc_ref, {
                    "round_points": rp,
                    "total_points": sum(rp.values()),
                    "games":        games,
                    "updated_at":   datetime.datetime.utcnow().isoformat(),
                })
            else:
                doc_ref = players_ref.document()
                batch.set(doc_ref, {
                    "Player":       player_name,
                    "Team":         team_name,
                    "total_points": points,
                    "round_points": {round_name: points},
                    "games": [{
                        "game_id":    str(game_id),
                        "date":       date_str,
                        "round":      round_name,
                        "points":     points,
                        "game_title": game_title,
                    }],
                    "created_at": datetime.datetime.utcnow().isoformat(),
                    "updated_at": datetime.datetime.utcnow().isoformat(),
                })

            batch_count += 1
            if batch_count >= MAX_BATCH:
                safe_batch_commit(batch)
                batch       = db.batch()
                batch_count = 0

    if batch_count > 0:
        safe_batch_commit(batch)

    update_submission_totals(year_str)
    st.success(f"🎉 Updated tournament points for {date_str} ({last_round})")


# ── Tournament leaderboard data ───────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_tournament_data() -> pd.DataFrame:
    """Load in-tournament player point totals from Firestore."""
    year_str = str(TOURNAMENT_YEAR)
    if tournament_data_exists(year_str):
        players = get_tournament_data_from_firestore(year_str)
        if players:
            return pd.DataFrame(players)
    return pd.DataFrame()