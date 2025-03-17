import streamlit as st
import pandas as pd
from firebase_util import get_submissions
from data_loader import load_tournament_data
from navigation import render_navigation

render_navigation()
st.title("🏆 Leaderboard")

def leaderboard_page():
    submissions = get_submissions()
    if not submissions:
        st.info("No team submissions available yet.")
        return

    # Create DataFrame from submissions
    teams_df = pd.DataFrame(submissions)
    teams_df = teams_df.rename(columns={"team_name": "Team Name", "total_points": "Points"})
    teams_df = teams_df.sort_values(by="Points", ascending=False).reset_index(drop=True)
    teams_df.insert(0, "Rank", teams_df.index + 1)
    teams_df["Rank"] = teams_df["Rank"].astype(str)
    teams_df["Points"] = teams_df["Points"].astype(str)

    # Reorder columns to: Rank, Team Name, Points
    teams_df = teams_df[["Rank", "Team Name", "Points"]]

    total_teams = len(submissions)
    player_freq = {}
    for submission in submissions:
        players = submission.get("players", [])
        for player in players:
            name = player if isinstance(player, str) else player.get("name", "")
            if name:
                player_freq[name] = player_freq.get(name, 0) + 1

    freq_df = pd.DataFrame(list(player_freq.items()), columns=["NAME", "Count"])
    freq_df["OWNED_float"] = (freq_df["Count"] / total_teams * 100).round(1)
    freq_df["OWNED"] = freq_df["OWNED_float"].astype(str) + "%"

    tournament_df = load_tournament_data()
    if tournament_df.empty:
        st.info("Tournament has not started yet.")
        return

    tournament_df = tournament_df.rename(columns={"Player": "NAME", "Team": "SCHOOL", "Seed": "SEED"})
    merged_df = pd.merge(freq_df, tournament_df[["NAME", "SCHOOL", "SEED", "Points"]], on="NAME", how="left")
    merged_df = merged_df.dropna(subset=["SCHOOL"])

    top5 = merged_df.sort_values(by="OWNED_float", ascending=False).head(5).reset_index(drop=True)
    top5.insert(0, "RANK", top5.index + 1)
    top5 = top5[["RANK", "NAME", "SCHOOL", "SEED", "OWNED"]]

    bottom5 = merged_df.sort_values(by="OWNED_float", ascending=True).head(5).reset_index(drop=True)
    bottom5.insert(0, "RANK", bottom5.index + 1)
    bottom5 = bottom5[["RANK", "NAME", "SCHOOL", "SEED", "OWNED"]]

    scorers_df = merged_df.sort_values(by="Points", ascending=False).reset_index(drop=True)
    scorers_df.insert(0, "RANK", scorers_df.index + 1)
    scorers_df["Points"] = scorers_df["Points"].astype(int).astype(str)
    scorers_table = scorers_df[["RANK", "NAME", "SCHOOL", "SEED", "Points", "OWNED"]]

    # Modified styling function with black text
    def highlight_top4_teams(row):
        styles = []
        for _ in row:
            if row.name < 4:
                styles.append('background-color: #90EE90; color: black')  # Green background with black text
            else:
                styles.append('')
        return styles

    # Apply styling to the teams_df table
    styled_teams = teams_df.style.apply(highlight_top4_teams, axis=1)

    col1, col2, col3 = st.columns([1, 1.3, 1.55])
    with col1:
        st.subheader("Team Leaderboard")
        st.dataframe(styled_teams, use_container_width=True, hide_index=True)
    with col2:
        st.subheader("Percentage Owned (Top 5)")
        st.dataframe(top5, use_container_width=True, hide_index=True)
        st.subheader("Percentage Owned (Bottom 5)")
        st.dataframe(bottom5, use_container_width=True, hide_index=True)
    with col3:
        st.subheader("Top Scorers for the Tournament")
        st.dataframe(scorers_table, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    leaderboard_page()