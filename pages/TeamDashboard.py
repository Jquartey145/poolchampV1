import streamlit as st
import pandas as pd
from firebase_util import get_submissions
from navigation import render_navigation

st.set_page_config(layout="wide")
render_navigation()
st.title("Team Dashboard")
st.markdown("Select a team from the dropdown to view its details.")

submissions = get_submissions()
if not submissions:
    st.info("No team submissions available yet.")
else:
    submissions_df = pd.DataFrame(submissions)
    team_names = submissions_df["team_name"].tolist()
    # Sort team names alphabetically
    team_names_sorted = sorted(team_names)
    selected_team = st.selectbox("Select a Team", team_names_sorted)

    submission = submissions_df[submissions_df["team_name"] == selected_team].iloc[0]

    st.markdown(f"### Team: {submission.get('team_name')}")
    st.markdown(f"**Participant Name:** {submission.get('participant')}")
    st.markdown(f"**Total Points:** {submission.get('total_points')}")

    players = submission.get("players", [])
    if players:
        # If players are stored as dictionaries, create a DataFrame with expected columns.
        if isinstance(players[0], dict):
            players_df = pd.DataFrame(players)
            # Ensure that "name", "team", "seed", and "position" columns exist.
            for col in ["name", "team", "seed", "position"]:
                if col not in players_df.columns:
                    players_df[col] = ""
            # Convert "seed" column to string
            players_df["seed"] = players_df["seed"].astype(str)
            # Rename columns to match the desired output
            players_df.rename(columns={"name": "Player Name"}, inplace=True)
            # Reorder columns to match the desired output
            players_df = players_df[["Player Name", "team", "seed", "position"]]
            # Rename remaining columns to match the desired output
            players_df.rename(columns={
                "team": "Team",
                "seed": "Seed",
                "position": "Position"
            }, inplace=True)
        else:
            # If players are simple strings, create a DataFrame with one column named "Player Name"
            players_df = pd.DataFrame(players, columns=["Player Name"])
            # Add missing columns with empty values
            for col in ["Team", "Seed", "Position"]:
                players_df[col] = ""
            # Ensure "Seed" is treated as a string
            players_df["Seed"] = players_df["Seed"].astype(str)

        players_df.reset_index(drop=True, inplace=True)
        st.markdown("#### Players")
        st.dataframe(players_df, use_container_width=True, hide_index=True)
    else:
        st.info("No players data found for this submission.")