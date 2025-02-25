import streamlit as st
import requests
import pandas as pd
import time
import random
from firebase_util import tournament_data_exists, get_tournament_data_from_firestore, save_player_data

API_KEY = "NjudaDDmMPylMayKIWkiXmZmQRa8j90VnnBypLBQ"
ACCESS_LEVEL = "trial"
LANGUAGE_CODE = "en"
BASE_URL = f"https://api.sportradar.com/ncaamb/{ACCESS_LEVEL}/v8/{LANGUAGE_CODE}"
TOURNAMENT_YEAR = 2023

def safe_get(data, keys, default=None):
    """Safely navigate nested dictionaries."""
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data

def fetch_with_retry(url, params, max_retries=5, base_delay=1.5):
    """Fetch data with an exponential backoff retry mechanism."""
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
    """Get team IDs and seeds from the tournament schedule."""
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
        for bracket in safe_get(round_data, ['bracketed'], []):
            for game in safe_get(bracket, ['games'], []):
                for side in ['home', 'away']:
                    if team := safe_get(game, [side, 'id']):
                        team_ids.add(team)
                        team_seeds[team] = safe_get(game, [side, 'seed'], "N/A")
    return list(team_ids), team_seeds

@st.cache_data(ttl=3600)
def load_tournament_data():
    """
    Load tournament data.
    First, check Firestore to see if data exists.
    If it does, return data from Firestore.
    Otherwise, fetch from the API, upload the data to Firestore,
    and then return the data.
    """
    year_str = str(TOURNAMENT_YEAR)
    if tournament_data_exists(year_str):
        players = get_tournament_data_from_firestore(year_str)
        if players:
            return pd.DataFrame(players)

    # Fetch data from the API if not available in Firestore
    url = f"{BASE_URL}/tournaments/{TOURNAMENT_YEAR}/PST/schedule.json"
    tournaments_data = fetch_with_retry(url, {"api_key": API_KEY})
    if not tournaments_data:
        return pd.DataFrame()

    ncaa_tournament_id = None
    for tournament in safe_get(tournaments_data, ['tournaments'], []):
        if "NCAA Men's Division I Basketball Tournament" in safe_get(tournament, ['name'], ''):
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
    # Upload the fetched data to Firestore
    player_list = df.to_dict(orient="records")
    save_player_data(year_str, player_list)
    return df
