import streamlit as st
import pandas as pd
import datetime
import time
import sportsdataverse.mbb as mbb
from firebase_util import (
    tournament_data_exists,
    get_tournament_data_from_firestore,
    save_player_data,
    get_regular_season_data,
    save_regular_season_data,
    update_submission_totals,
    db
)

TOURNAMENT_YEAR = 2025

# ── Round name detection ──────────────────────────────────────────────────────

ROUND_KEYWORDS = {
    "First Four":           "First Four",
    "First Round":          "Round 1",
    "Second Round":         "Round 2",
    "Sweet 16":             "Sweet 16",
    "Sweet Sixteen":        "Sweet 16",
    "Elite Eight":          "Elite 8",
    "Elite 8":              "Elite 8",
    "Final Four":           "Final 4",
    "National Championship":"Championship",
    "Championship":         "Championship",
}

def detect_round(headline: str) -> str:
    """Parse a round name from an ESPN notes headline."""
    if not isinstance(headline, str):
        return "Unknown Round"
    for keyword, round_name in ROUND_KEYWORDS.items():
        if keyword.lower() in headline.lower():
            return round_name
    return "Unknown Round"


# ── Firestore helpers ─────────────────────────────────────────────────────────

def safe_batch_commit(batch, max_retries=3):
    """Safely commit a Firestore batch with retries."""
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
    """Load tournament teams from Firestore (populated by TournamentAdmin page)."""
    docs = (
        db.collection("tournament_teams")
        .document(str(TOURNAMENT_YEAR))
        .collection("teams")
        .stream()
    )
    return [doc.to_dict() for doc in docs]


def save_tournament_teams(teams: list):
    """
    Save tournament teams to Firestore.
    teams: list of dicts with keys: team_name, seed, region
    """
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


# ── Regular season data (parquet — delay OK here) ─────────────────────────────

def build_regular_season_data(tournament_teams: list) -> pd.DataFrame:
    """
    Internal: load + aggregate regular season stats for a given list of tournament teams.
    Called by load_regular_season_data() and by TournamentAdmin after saving teams.
    Filters to seeds 1-16 (top 4 per region × 4 regions = 64 teams + 4 First Four).

    Args:
        tournament_teams: list of dicts with keys team_name, seed, region

    Returns DataFrame: Player, Team, Seed, Region, Position, Games, Points, PPG, FG%, 3P%
    """
    # Build lookup: team_display_name → {seed, region}
    team_meta = {
        t["team_name"]: {"seed": t["seed"], "region": t.get("region", "N/A")}
        for t in tournament_teams
        if t.get("seed") is not None and int(t["seed"]) <= 16
    }
    tournament_team_names = set(team_meta.keys())

    if not tournament_team_names:
        st.warning("No valid tournament teams (with seeds 1-16) found.")
        return pd.DataFrame()

    st.write(f"Loading regular season data for {len(tournament_team_names)} tournament teams...")

    # Load full season player boxscores via parquet (bulk, fast)
    try:
        box_df = mbb.load_mbb_player_boxscore(
            seasons=[TOURNAMENT_YEAR],
            return_as_pandas=True
        )
    except Exception as e:
        st.error(f"Failed to load player boxscore data: {str(e)}")
        return pd.DataFrame()

    if box_df is None or box_df.empty:
        st.warning("No player boxscore data returned.")
        return pd.DataFrame()

    # Filter to regular season (season_type == 2) and tournament teams only
    reg_df = box_df[
        (box_df["season_type"] == 2) &
        (box_df["team_display_name"].isin(tournament_team_names))
    ].copy()

    if reg_df.empty:
        st.warning(
            "No regular season data found for tournament teams. "
            "Team names may not match ESPN — check spelling in the admin table."
        )
        # Show what names ARE in the parquet to help debug
        actual = sorted(box_df["team_display_name"].dropna().unique().tolist())
        close = [n for n in actual if any(
            part.lower() in n.lower()
            for t in tournament_team_names
            for part in t.split()[:2]
        )]
        if close:
            st.info(f"Possible name matches in parquet: {close[:20]}")
        return pd.DataFrame()

    # Coerce numeric columns
    for col in ["points", "field_goals_made", "field_goals_attempted",
                "three_point_field_goals_made", "three_point_field_goals_attempted"]:
        if col in reg_df.columns:
            reg_df[col] = pd.to_numeric(reg_df[col], errors="coerce").fillna(0)

    # Aggregate per player across all regular season games
    player_stats = (
        reg_df.groupby(["athlete_display_name", "team_display_name"])
        .agg(
            Games=("points", "count"),
            Points=("points", "sum"),
            FG_made=("field_goals_made", "sum"),
            FG_att=("field_goals_attempted", "sum"),
            FG3_made=("three_point_field_goals_made", "sum"),
            FG3_att=("three_point_field_goals_attempted", "sum"),
        )
        .reset_index()
    )

    # Derived stats
    player_stats["PPG"] = (player_stats["Points"] / player_stats["Games"]).round(1)
    player_stats["FG%"] = (
        (player_stats["FG_made"] / player_stats["FG_att"].replace(0, float("nan"))) * 100
    ).round(1).fillna(0.0)
    player_stats["3P%"] = (
        (player_stats["FG3_made"] / player_stats["FG3_att"].replace(0, float("nan"))) * 100
    ).round(1).fillna(0.0)

    # Minimum sample filter
    player_stats = player_stats[player_stats["Games"] >= 5]

    # Add seed + region
    player_stats["Seed"] = player_stats["team_display_name"].map(
        lambda t: team_meta.get(t, {}).get("seed", "N/A")
    )
    player_stats["Region"] = player_stats["team_display_name"].map(
        lambda t: team_meta.get(t, {}).get("region", "N/A")
    )

    # Position (most common per player)
    if "athlete_position_abbreviation" in reg_df.columns:
        positions = (
            reg_df.groupby(["athlete_display_name", "team_display_name"])["athlete_position_abbreviation"]
            .agg(lambda x: x.mode()[0] if not x.mode().empty else "")
            .reset_index()
            .rename(columns={"athlete_position_abbreviation": "Position"})
        )
        player_stats = player_stats.merge(
            positions, on=["athlete_display_name", "team_display_name"], how="left"
        )
    else:
        player_stats["Position"] = ""

    # Rename and finalise
    player_stats = player_stats.rename(columns={
        "athlete_display_name": "Player",
        "team_display_name": "Team",
    })

    return player_stats[[
        "Player", "Team", "Seed", "Region", "Position",
        "Games", "Points", "PPG", "FG%", "3P%"
    ]].sort_values("Points", ascending=False)



@st.cache_data(ttl=3600)
def load_regular_season_data() -> pd.DataFrame:
    """
    Load regular season player stats for all tournament teams.
    Checks Firestore cache first (populated by TournamentAdmin after saving teams).
    Falls back to fetching from parquet if cache is missing.

    Returns DataFrame: Player, Team, Seed, Region, Position, Games, Points, PPG, FG%, 3P%
    """
    year_str = str(TOURNAMENT_YEAR)

    # Return from Firestore cache if available
    players = get_regular_season_data(year_str)
    if players:
        return pd.DataFrame(players)

    # Get tournament teams saved by TournamentAdmin page
    tournament_teams = _get_tournament_teams()
    if not tournament_teams:
        st.warning("No tournament teams found. Please use the Tournament Admin page to fetch teams first.")
        return pd.DataFrame()

    with st.spinner("Loading regular season player data..."):
        final_df = build_regular_season_data(tournament_teams)

    if final_df.empty:
        return pd.DataFrame()

    # Cache to Firestore for fast subsequent loads
    save_regular_season_data(year_str, final_df.to_dict(orient="records"))
    return final_df

# ── Tournament game updates (LIVE — espn_mbb_* functions) ────────────────────

def fetch_tournament_game_ids(date_str: str) -> list:
    """
    Get all tournament game IDs for a given date using the live ESPN schedule.
    date_str: "YYYY-MM-DD"
    Returns list of game_id integers.
    """
    try:
        # espn_mbb_schedule expects dates as YYYYMMDD integer
        date_int = int(date_str.replace("-", ""))
        schedule_df = mbb.espn_mbb_schedule(
            dates=date_int,
            season_type=3,          # 3 = postseason
            return_as_pandas=True
        )
        if schedule_df is None or schedule_df.empty:
            return []
        return schedule_df["game_id"].tolist()
    except Exception as e:
        st.warning(f"Could not fetch schedule for {date_str}: {e}")
        return []


def fetch_live_player_boxscore(game_id: int) -> tuple[pd.DataFrame, str]:
    """
    Fetch live player boxscore for a single game via ESPN API.
    Returns (player_df, notes_headline) tuple.

    Uses espn_mbb_pbp(raw=False) which returns a cleaned dict containing:
      - result["boxscore"]["players"] — list of team player stat blocks
      - result["header"]["competitions"][0]["notes"] — round headline

    espn_mbb_player_box does not exist in the Python package (only in R hoopR).
    """
    try:
        result = mbb.espn_mbb_pbp(game_id=game_id, raw=False)

        if not isinstance(result, dict):
            st.warning(f"Unexpected response type for game {game_id}: {type(result)}")
            return pd.DataFrame(), ""

        # ── Extract headline ──────────────────────────────────────────────────
        headline = ""
        try:
            header = result.get("header", {})
            if isinstance(header, dict):
                comps = header.get("competitions", [{}])
                if comps:
                    notes = comps[0].get("notes", [{}])
                    if notes:
                        headline = notes[0].get("headline", "")
        except Exception:
            pass

        # ── Extract player boxscore ───────────────────────────────────────────
        # result["boxscore"]["players"] is a list of team blocks, each with:
        #   { "team": {"displayName": ...}, "statistics": [{ "athletes": [...], "labels": [...] }] }
        boxscore = result.get("boxscore", {})
        team_blocks = boxscore.get("players", [])

        rows = []
        for team_block in team_blocks:
            team_name = team_block.get("team", {}).get("displayName", "")
            for stat_group in team_block.get("statistics", []):
                labels = stat_group.get("labels", [])   # e.g. ["MIN","FG","3PT","FT","OREB",...]
                for athlete_entry in stat_group.get("athletes", []):
                    athlete = athlete_entry.get("athlete", {})
                    player_name = athlete.get("displayName", "")
                    stats = athlete_entry.get("stats", [])   # values aligned to labels

                    row = {
                        "athlete_display_name": player_name,
                        "team_display_name": team_name,
                    }
                    for label, value in zip(labels, stats):
                        row[label] = value

                    rows.append(row)

        if not rows:
            st.warning(f"No player rows found in boxscore for game {game_id}")
            return pd.DataFrame(), headline

        player_df = pd.DataFrame(rows)

        # Normalise points column — ESPN label is "PTS"
        if "PTS" in player_df.columns:
            player_df["pts"] = pd.to_numeric(player_df["PTS"], errors="coerce").fillna(0)
        else:
            player_df["pts"] = 0

        return player_df, headline

    except Exception as e:
        st.warning(f"Could not fetch boxscore for game {game_id}: {e}")
        return pd.DataFrame(), ""


def update_daily_player_points(date_str: str):
    """
    Fetch live tournament game data for a given date and update Firestore.
    Uses espn_mbb_schedule (live) + espn_mbb_player_box (live) — no parquet lag.
    date_str: "YYYY-MM-DD"
    """
    st.write(f"🚀 Starting live player points update for {date_str}")

    year_str = str(TOURNAMENT_YEAR)

    # Get live game IDs for this date
    with st.spinner("Fetching today's tournament games from ESPN..."):
        game_ids = fetch_tournament_game_ids(date_str)

    if not game_ids:
        st.warning(f"⚠️ No tournament games found for {date_str}.")
        return

    st.write(f"🏀 Found {len(game_ids)} tournament game(s)")

    tournament_ref = db.collection("tournament_data").document(year_str)
    players_ref = tournament_ref.collection("players")

    batch = db.batch()
    batch_count = 0
    MAX_BATCH_SIZE = 400
    last_round_name = "Unknown Round"

    for game_id in game_ids:
        st.write(f"🔍 Fetching live boxscore for game {game_id}...")

        player_df, headline = fetch_live_player_boxscore(game_id)

        if player_df is None or player_df.empty:
            st.warning(f"⚠️ No player data for game {game_id}")
            continue

        round_name = detect_round(headline)
        if round_name != "Unknown Round":
            last_round_name = round_name

        game_title = headline if headline else f"Game {game_id}"
        st.write(f"  📋 {game_title} → {round_name}")

        # Coerce pts to numeric
        # Live ESPN boxscore may use "pts" or "points" depending on version
        pts_col = "pts" if "pts" in player_df.columns else "points"
        player_df[pts_col] = pd.to_numeric(player_df[pts_col], errors="coerce").fillna(0)

        for _, row in player_df.iterrows():
            player_name = row.get("athlete_display_name", "")
            team_name = row.get("team_display_name", "")
            points = int(row.get(pts_col, 0))

            if not player_name:
                continue

            st.write(f"    👤 {player_name} ({team_name}): {points} pts")

            # Look up existing Firestore doc
            existing = list(
                players_ref
                .where("Player", "==", player_name)
                .where("Team", "==", team_name)
                .limit(1)
                .stream()
            )

            if existing:
                doc_ref = players_ref.document(existing[0].id)
                current = existing[0].to_dict()
                round_points = current.get("round_points", {})
                round_points[round_name] = round_points.get(round_name, 0) + points
                total_points = sum(round_points.values())
                games = current.get("games", [])
                games.append({
                    "game_id": str(game_id),
                    "date": date_str,
                    "round": round_name,
                    "points": points,
                    "game_title": game_title,
                })
                batch.update(doc_ref, {
                    "round_points": round_points,
                    "total_points": total_points,
                    "games": games,
                    "updated_at": datetime.datetime.utcnow().isoformat(),
                })
            else:
                doc_ref = players_ref.document()
                batch.set(doc_ref, {
                    "Player": player_name,
                    "Team": team_name,
                    "total_points": points,
                    "round_points": {round_name: points},
                    "games": [{
                        "game_id": str(game_id),
                        "date": date_str,
                        "round": round_name,
                        "points": points,
                        "game_title": game_title,
                    }],
                    "created_at": datetime.datetime.utcnow().isoformat(),
                    "updated_at": datetime.datetime.utcnow().isoformat(),
                })

            batch_count += 1
            if batch_count >= MAX_BATCH_SIZE:
                st.write("🔄 Committing batch...")
                safe_batch_commit(batch)
                batch = db.batch()
                batch_count = 0

    if batch_count > 0:
        st.write("🔄 Committing final batch...")
        safe_batch_commit(batch)

    st.write("✅ Updating submission totals...")
    update_submission_totals(year_str)
    st.success(f"🎉 Updated tournament points for {date_str} ({last_round_name})")


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