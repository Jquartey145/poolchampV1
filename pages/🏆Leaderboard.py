import streamlit as st
import pandas as pd
from data_loader import load_tournament_data

def leaderboard_page():
    st.title("🏆 Leaderboard")

    # Load team submissions from session state
    submissions = st.session_state.get("submissions", [])

    if not submissions:
        st.info("No team submissions available yet.")
        return

    # ---------------------------------
    # 1. Create Team Leaderboard DataFrame
    # ---------------------------------
    teams_df = pd.DataFrame(submissions)
    teams_df = teams_df.rename(columns={"team_name": "Team Name", "total_points": "Points"})
    teams_df = teams_df.sort_values(by="Points", ascending=False).reset_index(drop=True)
    teams_df.insert(0, "Rank", teams_df.index + 1)

    # Convert Rank and Points to strings for better display
    teams_df["Rank"] = teams_df["Rank"].astype(str)
    teams_df["Points"] = teams_df["Points"].astype(str)

    # ---------------------------------
    # 2. Calculate Percentage Owned
    # ---------------------------------
    total_teams = len(submissions)
    player_freq = {}
    for submission in submissions:
        players = submission.get("players", [])
        for player in players:
            if player:
                player_freq[player] = player_freq.get(player, 0) + 1

    freq_df = pd.DataFrame(list(player_freq.items()), columns=["NAME", "Count"])
    freq_df["OWNED_float"] = (freq_df["Count"] / total_teams * 100).round(1)
    freq_df["OWNED"] = freq_df["OWNED_float"].astype(str) + "%"

    # ---------------------------------
    # 3. Merge Player Data from Tournament
    # ---------------------------------
    tournament_df = load_tournament_data()
    tournament_df = tournament_df.rename(columns={"Player": "NAME", "Team": "SCHOOL", "Seed": "SEED"})

    merged_df = pd.merge(freq_df, tournament_df[["NAME", "SCHOOL", "SEED"]], on="NAME", how="left")
    merged_df = merged_df.dropna(subset=["SCHOOL"])


    # ---------------------------------
    # 4. Top 5 and Bottom 5 Ownership
    # ---------------------------------
    top5 = merged_df.sort_values(by="OWNED_float", ascending=False).head(5).reset_index(drop=True)
    top5.insert(0, "RANK", top5.index + 1)
    top5 = top5[["RANK", "NAME", "SCHOOL", "SEED", "OWNED"]]

    bottom5 = merged_df.sort_values(by="OWNED_float", ascending=True).head(5).reset_index(drop=True)
    bottom5.insert(0, "RANK", bottom5.index + 1)
    bottom5 = bottom5[["RANK", "NAME", "SCHOOL", "SEED", "OWNED"]]

    # ---------------------------------
    # 5. Top Scorers for the Tournament
    # ---------------------------------
    scorers_df = pd.merge(freq_df, tournament_df[["NAME", "SCHOOL", "SEED", "Points"]], on="NAME", how="left")
    scorers_df = scorers_df.dropna(subset=["SCHOOL"])
    scorers_df["Points"] = pd.to_numeric(scorers_df["Points"], errors="coerce")

    scorers_df = scorers_df.sort_values(by="Points", ascending=False).reset_index(drop=True)
    scorers_df.insert(0, "RANK", scorers_df.index + 1)
    scorers_df["Rank"] = scorers_df["RANK"].astype(str)
    scorers_df["Points"] = scorers_df["Points"].astype(int).astype(str)

    scorers_table = scorers_df[["RANK", "NAME", "SCHOOL", "SEED", "Points", "OWNED"]]

    # ---------------------------------
    # Arrange Layout Using Columns
    # ---------------------------------
    col1, col2, col3 = st.columns([1, 1.3, 1.55])

    with col1:
        st.subheader("Team Leaderboard")
        st.dataframe(teams_df[["Rank", "Team Name", "Points"]], use_container_width=True, hide_index=True)

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
