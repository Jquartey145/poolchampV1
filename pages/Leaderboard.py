import streamlit as st
import pandas as pd
import datetime
import pytz
from firebase_util import get_submissions, db
from data_loader import load_tournament_data, load_regular_season_data, TOURNAMENT_YEAR
from navigation import render_navigation

render_navigation()
st.title("🏆 Leaderboard")


@st.cache_data(ttl=3600)
def get_cached_submissions():
    return get_submissions()


@st.cache_data(ttl=3600)
def get_cached_tournament_data():
    return load_tournament_data()


@st.cache_data(ttl=3600)
def get_cached_regular_season_data():
    return load_regular_season_data()


def leaderboard_page():
    submissions = get_cached_submissions()
    if not submissions:
        st.info("No team submissions available yet.")
        return

    ct         = pytz.timezone("America/Chicago")
    now_ct     = datetime.datetime.now(ct)
    deadline   = ct.localize(datetime.datetime(2026, 3, 19, 11, 0))
    tournament_started = now_ct >= deadline

    # ── Team leaderboard ──────────────────────────────────────────────────────
    teams_df = pd.DataFrame(submissions)
    teams_df = teams_df.rename(columns={"team_name": "Team Name", "total_points": "Points"})
    teams_df = teams_df.sort_values("Points", ascending=False).reset_index(drop=True)
    teams_df.insert(0, "Rank", (teams_df.index + 1).astype(str))
    teams_df["Points"] = teams_df["Points"].astype(str)
    teams_df = teams_df[["Rank", "Team Name", "Points"]]

    def highlight_top4(row):
        color = "background-color: #90EE90; color: black" if row.name < 4 else ""
        return [color] * len(row)

    styled_teams = teams_df.style.apply(highlight_top4, axis=1)

    if not tournament_started:
        st.subheader("Team Leaderboard")
        st.dataframe(styled_teams, use_container_width=True, hide_index=True)
        st.info("Full leaderboard stats will unlock when the tournament begins on March 19th.")
        return

    # ── Player ownership + tournament points ──────────────────────────────────
    total_teams = len(submissions)
    player_freq = {}
    for submission in submissions:
        for player in submission.get("players", []):
            name = player if isinstance(player, str) else player.get("name", "")
            if name:
                player_freq[name] = player_freq.get(name, 0) + 1

    freq_df = pd.DataFrame(list(player_freq.items()), columns=["NAME", "Count"])
    freq_df["OWNED_float"] = (freq_df["Count"] / total_teams * 100).round(1)
    freq_df["OWNED"]       = freq_df["OWNED_float"].astype(str) + "%"

    tournament_df = get_cached_tournament_data()
    if tournament_df.empty:
        st.subheader("Team Leaderboard")
        st.dataframe(styled_teams, use_container_width=True, hide_index=True)
        st.warning("Tournament player data not available yet.")
        return

    tournament_df = tournament_df.rename(columns={
        "Player": "NAME",
        "Team":   "SCHOOL",
    })

    # Pull seeds from regular season data
    reg_df = get_cached_regular_season_data()
    if isinstance(reg_df, list):
        reg_df = pd.DataFrame(reg_df)
    seed_map = reg_df.set_index("Player")["Seed"].to_dict() if not reg_df.empty else {}

    merged_df = pd.merge(
        freq_df,
        tournament_df[["NAME", "SCHOOL", "total_points"]],
        on="NAME",
        how="left"
    )
    merged_df = merged_df.dropna(subset=["SCHOOL"])
    merged_df["SEED"]   = merged_df["NAME"].map(seed_map)
    merged_df["Points"] = merged_df["total_points"].fillna(0).astype(int)

    # ── Top/bottom ownership ──────────────────────────────────────────────────
    top5 = (
        merged_df.sort_values("OWNED_float", ascending=False)
        .head(5)
        .reset_index(drop=True)
    )
    top5.insert(0, "RANK", top5.index + 1)
    top5 = top5[["RANK", "NAME", "SCHOOL", "SEED", "OWNED"]]

    bottom5 = (
        merged_df[pd.to_numeric(merged_df["SEED"], errors="coerce").between(1, 5)]
        .sort_values("OWNED_float", ascending=True)
        .head(5)
        .reset_index(drop=True)
    )
    bottom5.insert(0, "RANK", bottom5.index + 1)
    bottom5 = bottom5[["RANK", "NAME", "SCHOOL", "SEED", "OWNED"]]

    # ── Top scorers ───────────────────────────────────────────────────────────
    scorers_df = (
        merged_df.sort_values("Points", ascending=False)
        .reset_index(drop=True)
    )
    scorers_df.insert(0, "RANK", scorers_df.index + 1)
    scorers_df["Points"] = scorers_df["Points"].astype(str)
    scorers_table = scorers_df[["RANK", "NAME", "SCHOOL", "SEED", "Points", "OWNED"]]

    # ── Layout ────────────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1.2, 1.2, 1.55])

    with col1:
        st.subheader("Team Leaderboard")
        st.dataframe(styled_teams, use_container_width=True, hide_index=True)

    with col2:
        st.subheader("Most Owned (Top 5)")
        st.dataframe(top5, use_container_width=True, hide_index=True)
        st.subheader("Least Owned (Seeds 1-5)")
        st.dataframe(bottom5, use_container_width=True, hide_index=True)

    with col3:
        st.subheader("Top Tournament Scorers")
        st.dataframe(scorers_table, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    leaderboard_page()