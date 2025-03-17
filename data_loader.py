import streamlit as st
import requests
import pandas as pd
import time
import random
import datetime
from firebase_util import (
    tournament_data_exists,
    get_tournament_data_from_firestore,
    save_player_data,
    get_net_rankings,
    save_net_rankings,
    get_top16_player_data,
    save_top16_player_data,
    get_regular_season_data,
    save_regular_season_data
)
from google.cloud.firestore_v1 import WriteBatch

API_KEY = "ON3UvFxCKhEVsiZorA4AJ01jhpKKI25ZcRm1TYzq"
ACCESS_LEVEL = "trial"
LANGUAGE_CODE = "en"
BASE_URL = f"https://api.sportradar.com/ncaamb/{ACCESS_LEVEL}/v8/{LANGUAGE_CODE}"
TOURNAMENT_YEAR = 2024

def safe_get(data, keys, default=None):
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data

def fetch_with_retry(url, params, max_retries=5, base_delay=1.5):
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params)
            if response.status_code == 429:
                wait_time = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                time.sleep(wait_time)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException:
            time.sleep(base_delay * (2 ** attempt))
    return None

@st.cache_data(ttl=3600)
def get_tournament_teams_and_seeds(tournament_id):
    url = f"{BASE_URL}/tournaments/{tournament_id}/summary.json"
    data = fetch_with_retry(url, {"api_key": API_KEY})
    if not data:
        return [], {}, {}
    team_ids = set()
    team_seeds = {}
    team_regions = {}
    # Iterate over each bracket in the summary data
    for bracket in safe_get(data, ["brackets"], []):
        # Extract the region name from the bracket's name and trim "Regional" if present.
        region = bracket.get("name", "")
        if region.endswith("Regional"):
            region = region[:-len("Regional")].strip()
        for participant in safe_get(bracket, ["participants"], []):
            team_id = participant.get("id")
            if team_id:
                team_ids.add(team_id)
                team_seeds[team_id] = participant.get("seed", "N/A")
                team_regions[team_id] = region
    return list(team_ids), team_seeds, team_regions

@st.cache_data(ttl=3600)
def load_tournament_data():
    """
    Load tournament data. If data exists in Firestore, return it.
    Otherwise, fetch from the API, add "Team_ID" for filtering, and store it.
    If the tournament status is "scheduled", return an empty DataFrame.
    """
    year_str = str(TOURNAMENT_YEAR)
    if tournament_data_exists(year_str):
        players = get_tournament_data_from_firestore(year_str)
        if players:
            return pd.DataFrame(players)

    url = f"{BASE_URL}/tournaments/{TOURNAMENT_YEAR}/PST/schedule.json"
    tournaments_data = fetch_with_retry(url, {"api_key": API_KEY})
    if not tournaments_data:
        return pd.DataFrame()

    ncaa_tournament_id = None
    # Iterate through tournaments to find the NCAA tournament and check its status.
    for tournament in safe_get(tournaments_data, ['tournaments'], []):
        tournament_name = safe_get(tournament, ['name'], '')
        if "NCAA Men's Division I Basketball Tournament" in tournament_name:
            tournament_status = tournament.get("status", "").lower()
            if tournament_status == "scheduled":
                # If tournament status is scheduled, return an empty DataFrame.
                return pd.DataFrame()
            ncaa_tournament_id = safe_get(tournament, ['id'])
            break

    if not ncaa_tournament_id:
        return pd.DataFrame()

    team_ids, team_seeds, team_regions = get_tournament_teams_and_seeds(ncaa_tournament_id)
    all_players = pd.DataFrame()
    for team_id in team_ids:
        url = f"{BASE_URL}/tournaments/{ncaa_tournament_id}/teams/{team_id}/statistics.json"
        stats_data = fetch_with_retry(url, {"api_key": API_KEY})
        if not stats_data:
            continue
        team_players = []
        for player in safe_get(stats_data, ['players'], []):
            team_players.append({
                "Player": safe_get(player, ['full_name'], 'Unknown'),
                "Team": safe_get(stats_data, ['team', 'market'], 'Unknown'),
                "Team_ID": team_id,  # Save team id for filtering later.
                "Seed": team_seeds.get(team_id, "N/A"),
                "Region": team_regions.get(team_id, "N/A"),  # Include region from team_regions
                "Position": safe_get(player, ['position'], ''),
                "Games": safe_get(player, ['total', 'games_played'], 0),
                "Points": safe_get(player, ['total', 'points'], 0),
                "PPG": safe_get(player, ['average', 'points'], 0.0),
                "FG%": round(safe_get(player, ['total', 'field_goals_pct'], 0.0) * 100, 1),
                "3P%": round(safe_get(player, ['total', 'three_points_pct'], 0.0) * 100, 1),
                "round_points": {  # Track points in each round
                    "First Four": 0,
                    "Round 1": 0,
                    "Round 2": 0,
                    "Sweet 16": 0,
                    "Elite 8": 0,
                    "Final 4": 0,
                    "Championship": 0
                },
                "total_tournament_points": 0  # Track total points in the tournament
            })
        all_players = pd.concat([all_players, pd.DataFrame(team_players)], ignore_index=True)
    df = all_players.sort_values('Points', ascending=False)
    player_list = df.to_dict(orient="records")
    save_player_data(year_str, player_list)
    return df

@st.cache_data(ttl=3600)
def load_net_rankings():
    """
    Load net rankings from Sportradar.
    Check Firestore for stored data; if older than one week, update it.
    """
    year_str = str(TOURNAMENT_YEAR)
    net_rankings = get_net_rankings(year_str)
    update = False
    if net_rankings is None:
        update = True
    else:
        last_updated = net_rankings.get("last_updated")
        if last_updated:
            last_updated_dt = datetime.datetime.fromisoformat(last_updated)
            if datetime.datetime.now() - last_updated_dt > datetime.timedelta(weeks=1):
                update = True
        else:
            update = True
    if update:
        url = f"{BASE_URL}/seasons/{TOURNAMENT_YEAR}/REG/netrankings.json"
        params = {"api_key": API_KEY}
        data = fetch_with_retry(url, params)
        if not data:
            return None
        rankings = data.get("rankings", [])[:16]
        top16 = []
        for item in rankings:
            team_id = item.get("id")
            team_name = item.get("market")
            rank = item.get("net_rank")
            top16.append({"team_id": team_id, "team_name": team_name, "rank": rank})
        save_net_rankings(year_str, top16)
        net_rankings = {"top16": top16, "last_updated": datetime.datetime.now().isoformat()}
    return net_rankings

@st.cache_data(ttl=3600)
def load_top16_player_data():
    """
    Load player data for the top 16 teams from NET rankings, using "Seed" instead of "Rank".
    If data exists in Firestore, return it.
    Otherwise, fetch from the API, add "Team_ID" and "Seed" for filtering, and store it.
    """
    year_str = str(TOURNAMENT_YEAR)

    # Check if data already exists in Firestore
    players = get_top16_player_data(year_str)
    if players:
        return pd.DataFrame(players)

    # Get top 16 teams from NET rankings (with rank)
    net_rankings = load_net_rankings()
    if not net_rankings:
        return pd.DataFrame()

    top16_teams = [
        {"team_id": team["team_id"], "seed": team["rank"]}  # Rename 'rank' to 'seed'
        for team in net_rankings.get("top16", [])
        if team.get("team_id") and "rank" in team
    ]

    if not top16_teams:
        return pd.DataFrame()

    all_players = pd.DataFrame()

    # Fetch player stats for each top 16 team
    for team in top16_teams:
        team_id = team["team_id"]
        team_seed = team["seed"]  # Store rank as seed

        url = f"{BASE_URL}/seasons/{TOURNAMENT_YEAR}/REG/teams/{team_id}/statistics.json"
        stats_data = fetch_with_retry(url, {"api_key": API_KEY})

        if not stats_data:
            st.warning(f"Unable to load data for team {team_id}")
            continue  # Skip this team if no data is found

        team_players = []
        for player in safe_get(stats_data, ['players'], []):
            team_players.append({
                "Player": safe_get(player, ['full_name'], 'Unknown'),
                "Team": safe_get(stats_data, ['market'], 'Unknown'),
                "Team_ID": team_id,
                "Seed": team_seed,  # Store the rank from NET rankings but call it "Seed"
                "Region": "N/A",  # Default region for top 16 players (not available in NET rankings)
                "Position": safe_get(player, ['position'], ''),
                "Games": safe_get(player, ['total', 'games_played'], 0),
                "Points": safe_get(player, ['total', 'points'], 0),
                "PPG": safe_get(player, ['average', 'points'], 0.0),
                "FG%": round(safe_get(player, ['total', 'field_goals_pct'], 0.0) * 100, 1),
                "3P%": round(safe_get(player, ['total', 'three_points_pct'], 0.0) * 100, 1)
            })

        all_players = pd.concat([all_players, pd.DataFrame(team_players)], ignore_index=True)

    # Sort players by total points
    df = all_players.sort_values('Points', ascending=False)

    # Save data to Firestore
    if not df.empty:
        player_list = df.to_dict(orient="records")
        save_top16_player_data(year_str, player_list)

    return df

# In data_loader.py

@st.cache_data(ttl=3600)
def fetch_daily_change_log(date: str):
    """Fetch game IDs for a specific date from daily change log"""
    year, month, day = date.split("-")
    url = f"{BASE_URL}/league/{year}/{month}/{day}/changes.json"
    params = {"api_key": API_KEY}
    data = fetch_with_retry(url, params)
    return [game["id"] for game in safe_get(data, ["results"], []) if safe_get(game, ["id"])]

@st.cache_data(ttl=3600)
def fetch_game_details(game_id: str):
    """Fetch game summary and extract round name + player points"""
    url = f"{BASE_URL}/games/{game_id}/summary.json"
    data = fetch_with_retry(url, {"api_key": API_KEY})
    if not data:
        return None, []

    # Extract round name from game title
    game_title = safe_get(data, ["game", "title"], "")
    round_name = None

    # Match game title to known round names
    for round in ["First Four", "First Round", "Second Round", "Sweet 16", "Elite Eight", "Final Four", "National Championship"]:
        if round in game_title:
            round_name = round
            break

    # Default to "Unknown Round" if no match is found
    if not round_name:
        round_name = "Unknown Round"

    # Extract player points from both teams
    player_data = []
    for team_type in ["home", "away"]:
        team = safe_get(data, ["game", team_type], {})
        team_id = safe_get(team, ["id"], "")

        for player in safe_get(team, ["players"], []):
            player_data.append({
                "team_id": team_id,
                "player_name": safe_get(player, ["full_name"], "Unknown"),
                "points": safe_get(player, ["statistics", "points"], 0),
                "round": round_name,
                "game_id": game_id,
                "game_title": game_title
            })

    return round_name, player_data

def update_daily_player_points(date: str):
    """Process daily games with batched writes, audit timestamps, and error handling"""
    game_ids = fetch_daily_change_log(date)
    if not game_ids:
        st.warning(f"No games found for {date}")
        return

    # Get Firestore references
    db = firestore.client()
    year_str = str(TOURNAMENT_YEAR)
    tournament_ref = db.collection("tournament_data").document(year_str)
    players_ref = tournament_ref.collection("players")

    batch = db.batch()
    batch_count = 0
    MAX_BATCH_SIZE = 500  # Firestore batch limit

    # Process each game
    for game_id in game_ids:
        round_name, game_players = fetch_game_details(game_id)
        if not game_players:
            continue

        for gp in game_players:
            # Query for existing player
            query = players_ref.where("Player", "==", gp["player_name"]) \
                              .where("Team_ID", "==", gp["team_id"]) \
                              .limit(1)
            docs = list(query.stream())

            # Prepare game update data
            game_update = {
                "game_id": game_id,
                "date": date,
                "round": round_name,
                "points": gp["points"],
                "game_title": gp["game_title"],
                "timestamp": firestore.SERVER_TIMESTAMP
            }

            # Prepare base update data
            update_data = {
                "total_points": firestore.Increment(gp["points"]),
                f"round_points.{round_name}": firestore.Increment(gp["points"]),
                "updated_at": firestore.SERVER_TIMESTAMP
            }

            # Only add game history if points are greater than 0
            if gp["points"] > 0:
                update_data["games"] = firestore.ArrayUnion([game_update])

            if docs:
                # Existing document - update operation
                doc_ref = docs[0].reference
                batch.update(doc_ref, update_data)
            else:
                # New document - create operation
                new_doc_ref = players_ref.document()
                new_player = {
                    "Player": gp["player_name"],
                    "Team_ID": gp["team_id"],
                    "total_points": gp["points"],
                    "round_points": {round_name: gp["points"]},
                    "games": [game_update] if gp["points"] > 0 else [],
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "updated_at": firestore.SERVER_TIMESTAMP
                }
                batch.set(new_doc_ref, new_player)

            # Commit batch when reaching limit
            batch_count += 1
            if batch_count >= MAX_BATCH_SIZE:
                safe_batch_commit(batch)
                batch = db.batch()
                batch_count = 0

    # Commit remaining operations
    if batch_count > 0:
        safe_batch_commit(batch)

    st.success(f"Processed {len(game_ids)} games with {batch_count} updates")

def safe_batch_commit(batch, max_retries=3):
    """Helper function to safely commit Firestore batches with retries"""
    for attempt in range(max_retries):
        try:
            batch.commit()
            return
        except Exception as e:
            if attempt == max_retries - 1:
                st.error(f"Failed to commit batch after {max_retries} attempts: {str(e)}")
                raise
            time.sleep(2 ** attempt)  # Exponential backoff


def get_ncaa_tournament_id():
    """Fetch the NCAA tournament ID for the current year, regardless of status."""
    url = f"{BASE_URL}/tournaments/{TOURNAMENT_YEAR}/PST/schedule.json"
    tournaments_data = fetch_with_retry(url, {"api_key": API_KEY})
    if not tournaments_data:
        return None
    for tournament in safe_get(tournaments_data, ['tournaments'], []):
        tournament_name = safe_get(tournament, ['name'], '')
        if "NCAA Men's Division I Basketball Tournament" in tournament_name:
            return safe_get(tournament, ['id'])
    return None

@st.cache_data(ttl=3600)
def load_regular_season_data():
    """Load regular season stats for teams in the NCAA tournament."""
    year_str = str(TOURNAMENT_YEAR)

    # Check Firestore for existing data
    players = get_regular_season_data(year_str)
    if players:
        # Check if data is fresh (within 7 days)
        last_updated = players.get("last_updated")
        if last_updated:
            last_updated_dt = datetime.datetime.fromisoformat(last_updated)
            if (datetime.datetime.now() - last_updated_dt) < datetime.timedelta(days=7):
                return pd.DataFrame(players["players"])

    # Fetch tournament teams and seeds
    tournament_id = get_ncaa_tournament_id()
    if not tournament_id:
        return pd.DataFrame()
    team_ids, team_seeds, team_regions = get_tournament_teams_and_seeds(tournament_id)
    if not team_ids:
        return pd.DataFrame()

    # Fetch regular season stats for each team
    all_players = []
    for team_id in team_ids:
        url = f"{BASE_URL}/seasons/{TOURNAMENT_YEAR}/REG/teams/{team_id}/statistics.json"
        stats_data = fetch_with_retry(url, {"api_key": API_KEY})
        if not stats_data:
            continue
        for player in safe_get(stats_data, ['players'], []):
            all_players.append({
                "Player": safe_get(player, ['full_name'], 'Unknown'),
                "Team": safe_get(stats_data, ['market'], 'Unknown'),
                "Team_ID": team_id,
                "Seed": team_seeds.get(team_id, "N/A"),
                "Region": team_regions.get(team_id, "N/A"),
                "Position": safe_get(player, ['position'], ''),
                "Games": safe_get(player, ['total', 'games_played'], 0),
                "Points": safe_get(player, ['total', 'points'], 0),
                "PPG": safe_get(player, ['average', 'points'], 0.0),
                "FG%": round(safe_get(player, ['total', 'field_goals_pct'], 0.0) * 100, 1),
                "3P%": round(safe_get(player, ['total', 'three_points_pct'], 0.0) * 100, 1)
            })

    df = pd.DataFrame(all_players).sort_values('Points', ascending=False)
    save_regular_season_data(year_str, df.to_dict(orient='records'))
    return df