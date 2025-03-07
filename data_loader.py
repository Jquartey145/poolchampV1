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
    save_top16_player_data
)

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
    url = f"{BASE_URL}/tournaments/{tournament_id}/schedule.json"
    data = fetch_with_retry(url, {"api_key": API_KEY})
    if not data:
        return [], {}
    team_ids = set()
    team_seeds = {}
    for round_data in safe_get(data, ['rounds'], []):
        for game in safe_get(round_data, ['games'], []):
            for side in ['home', 'away']:
                if team := safe_get(game, [side, 'id']):
                    team_ids.add(team)
                    team_seeds[team] = safe_get(game, [side, 'seed'], "N/A")
        for bracket in safe_get(data, ['bracketed'], []):
            for game in safe_get(bracket, ['games'], []):
                for side in ['home', 'away']:
                    if team := safe_get(game, [side, 'id']):
                        team_ids.add(team)
                        team_seeds[team] = safe_get(game, [side, 'seed'], "N/A")
    return list(team_ids), team_seeds

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

    team_ids, team_seeds = get_tournament_teams_and_seeds(ncaa_tournament_id)
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
                "Position": safe_get(player, ['position'], ''),
                "Games": safe_get(player, ['total', 'games_played'], 0),
                "Points": safe_get(player, ['total', 'points'], 0),
                "PPG": safe_get(player, ['average', 'points'], 0.0),
                "FG%": round(safe_get(player, ['total', 'field_goals_pct'], 0.0) * 100, 1),
                "3P%": round(safe_get(player, ['total', 'three_points_pct'], 0.0) * 100, 1)
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
