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
    selected_team = st.selectbox("Select a Team", team_names)

    submission = submissions_df[submissions_df["team_name"] == selected_team].iloc[0]

    st.markdown(f"### Team: {submission.get('team_name')}")
    st.markdown(f"**Participant:** {submission.get('participant')}")
    st.markdown(f"**Total Points:** {submission.get('total_points')}")

    players = submission.get("players", [])
    if players:
        # If players are stored as dictionaries, create a DataFrame with expected columns.
        if isinstance(players[0], dict):
            players_df = pd.DataFrame(players)
            # Ensure that "name", "team", and "seed" columns exist.
            for col in ["name", "team", "seed"]:
                if col not in players_df.columns:
                    players_df[col] = ""
            # Rename "Points" column to "Total Points" if it exists.
            if "Points" in players_df.columns:
                players_df.rename(columns={"Points": "Total Points"}, inplace=True)
            # Optionally, reorder the columns so that name, team, and seed come first.
            cols_order = ["name", "team", "seed"] + [col for col in players_df.columns if col not in ["name", "team", "seed"]]
            players_df = players_df[cols_order]
        else:
            # If players are simple strings, create a DataFrame with one column named "players"
            players_df = pd.DataFrame(players, columns=["Players"])
        players_df.reset_index(drop=True, inplace=True)
        st.markdown("#### Players")
        st.dataframe(players_df, use_container_width=True, hide_index=True)
    else:
        st.info("No players data found for this submission.")
