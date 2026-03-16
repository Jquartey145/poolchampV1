import streamlit as st
import pandas as pd
import datetime
import pytz
from firebase_util import get_submissions, db
from navigation import render_navigation
from data_loader import load_tournament_data, TOURNAMENT_YEAR

st.set_page_config(layout="wide")
render_navigation()

@st.cache_data(ttl=3600)
def get_cached_submissions():
    return get_submissions()

@st.cache_data(ttl=3600)
def get_cached_tournament_data(year: str):
    tournament_doc   = db.collection("tournament_data").document(year)
    players_collection = tournament_doc.collection("players")
    return [player.to_dict() for player in players_collection.stream()]

def display_team_dashboard():
    st.title("Team Dashboard")

    submissions = get_cached_submissions()
    if not submissions:
        st.warning("No submissions found.")
        return

    ct     = pytz.timezone("America/Chicago")
    now_ct = datetime.datetime.now(ct)

    # Dashboard unlocks when Round 1 tips off — March 19 2026 at 11:00 AM CT
    naive_deadline = datetime.datetime(2026, 3, 19, 11, 0)
    deadline = ct.localize(naive_deadline)

    if now_ct < deadline:
        st.write("Dashboard will unlock at 11:00 AM CT on March 19th")
        st.stop()

    st.markdown("Select a team from the dropdown to view its details.")

    submissions_df   = pd.DataFrame(submissions)
    team_names_sorted = sorted(submissions_df["team_name"].tolist())
    selected_team    = st.selectbox("Select a Team", team_names_sorted)

    submission = submissions_df[submissions_df["team_name"] == selected_team].iloc[0]

    st.markdown(f"### Team: {submission.get('team_name')}")
    st.markdown(f"**Participant Name:** {submission.get('participant')}")
    st.markdown(f"**Total Points:** {submission.get('total_points')}")

    players = submission.get("players", [])
    if not players:
        st.warning("No players found for this submission.")
        return

    players_df = pd.DataFrame(players)

    year_str       = str(TOURNAMENT_YEAR)
    cached_players = get_cached_tournament_data(year_str)

    player_points_map = {p["Player"]: p.get("round_points", {}) for p in cached_players}

    round_columns = ["First Four", "Round 1", "Round 2", "Sweet 16", "Elite 8", "Final 4", "Championship"]
    for round_name in round_columns:
        players_df[round_name] = 0

    for index, player in players_df.iterrows():
        player_name  = player.get("name")
        if not player_name:
            continue
        round_points = player_points_map.get(player_name, {})
        for round_name in round_columns:
            players_df.at[index, round_name] = round_points.get(round_name, 0)

    display_columns = ["name", "team", "seed", "position"] + round_columns
    players_df = players_df[display_columns]
    players_df = players_df.rename(columns={
        "name":     "Player Name",
        "team":     "Team",
        "seed":     "Seed",
        "position": "Position",
    })

    st.markdown("#### Players")
    st.dataframe(players_df, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    display_team_dashboard()