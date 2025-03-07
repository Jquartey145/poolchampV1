import streamlit as st
import requests
import pandas as pd
import time
import random
from datetime import datetime

API_KEY = "yZuetrZFGRW4eknkRH44dvTo6n6RSNz2KCT3DAnG"
ACCESS_LEVEL = "trial"
LANGUAGE_CODE = "en"
BASE_URL = f"https://api.sportradar.com/ncaamb/{ACCESS_LEVEL}/v8/{LANGUAGE_CODE}"

def safe_get(data, keys, default=None):
    """Safely navigate nested dictionaries"""
    for key in keys:
        try:
            data = data[key]
        except (KeyError, TypeError, IndexError):
            return default
    return data

def fetch_with_retry(url, params, max_retries=5, base_delay=1.5):
    """Fetch data with exponential backoff retry mechanism."""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params)
            if response.status_code == 429:  # Rate limited
                wait_time = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                st.warning(f"Rate limit hit, retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
                continue  # Retry the request

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching data (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(base_delay * (2 ** attempt))  # Exponential backoff

    return None  # Return None if all retries fail

@st.cache_data(ttl=3600)
def get_tournament_teams_and_seeds(tournament_id):
    """Get all team IDs and their seeds participating in the tournament"""
    time.sleep(1)  # Prevent rapid API calls
    url = f"{BASE_URL}/tournaments/{tournament_id}/schedule.json"
    data = fetch_with_retry(url, {"api_key": API_KEY})

    if not data:
        return [], {}

    team_ids = set()
    team_seeds = {}  # Dictionary to store team IDs and their seeds

    for round_data in safe_get(data, ['rounds'], []):
        for game in safe_get(round_data, ['games'], []):
            for side in ['home', 'away']:
                if team := safe_get(game, [side, 'id']):
                    team_ids.add(team)
                    # Extract seed if available
                    seed = safe_get(game, [side, 'seed'], None)
                    if seed:
                        team_seeds[team] = seed

        for bracket in safe_get(round_data, ['bracketed'], []):
            for game in safe_get(bracket, ['games'], []):
                for side in ['home', 'away']:
                    if team := safe_get(game, [side, 'id']):
                        team_ids.add(team)
                        # Extract seed if available
                        seed = safe_get(game, [side, 'seed'], None)
                        if seed:
                            team_seeds[team] = seed

    return list(team_ids), team_seeds

@st.cache_data(ttl=3600)
def get_team_player_stats(tournament_id, team_id, team_seeds):
    """Fetch player stats for a team using fetch_with_retry."""
    time.sleep(1.5)  # Prevent hitting API too fast
    url = f"{BASE_URL}/tournaments/{tournament_id}/teams/{team_id}/statistics.json"
    stats_data = fetch_with_retry(url, {"api_key": API_KEY})

    if not stats_data:
        return pd.DataFrame()

    players = []
    for player in safe_get(stats_data, ['players'], []):
        players.append({
            "Player": safe_get(player, ['full_name'], 'Unknown'),
            "Team": safe_get(stats_data, ['team', 'market'], 'Unknown'),
            "Seed": team_seeds.get(team_id, "N/A"),  # Add seed to player stats
            "Position": safe_get(player, ['position'], ''),
            "Games": safe_get(player, ['total', 'games_played'], 0),
            "Points": safe_get(player, ['total', 'points'], 0),
            "PPG": safe_get(player, ['average', 'points'], 0.0),
            "Rebounds": safe_get(player, ['total', 'rebounds'], 0),
            "Assists": safe_get(player, ['total', 'assists'], 0),
            "Steals": safe_get(player, ['total', 'steals'], 0),
            "Blocks": safe_get(player, ['total', 'blocks'], 0),
            "FG%": round(safe_get(player, ['total', 'field_goals_pct'], 0.0) * 100, 1),
            "3P%": round(safe_get(player, ['total', 'three_points_pct'], 0.0) * 100, 1)
        })

    return pd.DataFrame(players)

# Streamlit App
st.title("🏀 March Madness Player Statistics")
st.markdown("### NCAA Tournament Player Performance")

# Hardcoded latest available tournament year
TOURNAMENT_YEAR = 2023  # Update manually each year

@st.cache_data(ttl=3600)
def load_tournament_data(year):
    """Load tournament data with player stats."""
    url = f"{BASE_URL}/tournaments/{year}/PST/schedule.json"
    tournaments_data = fetch_with_retry(url, {"api_key": API_KEY})

    if not tournaments_data:
        st.error("Could not fetch tournament data")
        return pd.DataFrame()

    ncaa_tournament_id = None
    for tournament in safe_get(tournaments_data, ['tournaments'], []):
        if "NCAA Men's Division I Basketball Tournament" in safe_get(tournament, ['name'], ''):
            ncaa_tournament_id = safe_get(tournament, ['id'])
            break

    if not ncaa_tournament_id:
        st.error("Could not find NCAA Tournament ID")
        return pd.DataFrame()

    # Get all team IDs and their seeds in the tournament
    team_ids, team_seeds = get_tournament_teams_and_seeds(ncaa_tournament_id)

    # Collect stats from all teams
    all_players = pd.DataFrame()
    for team_id in team_ids:
        team_df = get_team_player_stats(ncaa_tournament_id, team_id, team_seeds)
        if not team_df.empty:
            all_players = pd.concat([all_players, team_df], ignore_index=True)

    return all_players.sort_values('Points', ascending=False)

df = load_tournament_data(TOURNAMENT_YEAR)

if not df.empty:
    # Sidebar Filters
    st.sidebar.header("Filters")

    # Dropdown for Team filter
    teams = ["All Teams"] + sorted(df["Team"].unique())
    selected_team = st.sidebar.selectbox("Select Team", teams)

    # Dropdown for Position filter
    positions = ["All Positions"] + sorted(df["Position"].dropna().unique())
    selected_position = st.sidebar.selectbox("Select Position", positions)

    # Apply filters
    filtered_df = df.copy()
    if selected_team != "All Teams":
        filtered_df = filtered_df[filtered_df["Team"] == selected_team]

    if selected_position != "All Positions":
        filtered_df = filtered_df[filtered_df["Position"] == selected_position]

    # Display stats
    st.write(f"Showing stats for {TOURNAMENT_YEAR} NCAA Tournament:")
    st.dataframe(
        filtered_df,
        column_config={
            "PPG": st.column_config.NumberColumn(format="%.1f"),
            "FG%": st.column_config.NumberColumn(format="%.1f"),
            "3P%": st.column_config.NumberColumn(format="%.1f")
        },
        hide_index=True,
        use_container_width=True,
        height=600
    )

    # Metrics
    st.subheader("Tournament Leaders")
    cols = st.columns(3)
    with cols[0]:
        st.metric("Top Scorer",
                 filtered_df.iloc[0]['Points'],
                 filtered_df.iloc[0]['Player'])
    with cols[1]:
        rebounds_leader = filtered_df.loc[filtered_df['Rebounds'].idxmax()]
        st.metric("Rebounds Leader",
                 rebounds_leader['Rebounds'],
                 rebounds_leader['Player'])
    with cols[2]:
        assists_leader = filtered_df.loc[filtered_df['Assists'].idxmax()]
        st.metric("Assists Leader",
                 assists_leader['Assists'],
                 assists_leader['Player'])

else:
    st.warning("No player data available. Check your API key or try again later.")