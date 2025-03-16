import streamlit as st
import pandas as pd
from data_loader import load_tournament_data, load_top16_player_data, load_net_rankings
from navigation import render_navigation

st.set_page_config(layout="wide")
render_navigation()
st.title("🏀 March Madness Player Statistics")

# Load player data
tournament_data = load_tournament_data()
if tournament_data.empty:
    st.warning("Tournament data not available. Falling back to top 16 player data.")
    data = load_top16_player_data()
    use_tournament_data = False
else:
    data = tournament_data
    use_tournament_data = True

if use_tournament_data:
    st.markdown("### NCAA Regular Season Player Performance")
else:
    st.markdown("### NCAA Current Season Player Performance")
df = pd.DataFrame(data)

# Drop unnecessary columns
df = df.drop(columns=["round_points", "total_tournament_points"], errors="ignore")

# Load net rankings
net_rankings = load_net_rankings()
if not net_rankings:
    st.warning("Unable to load NET rankings.")
    net_rankings = {"top16": []}  # Fallback in case data is not available

# Create a dictionary to map team names to their net rankings
team_rankings = {team["team_name"]: team["rank"] for team in net_rankings.get("top16", [])}

if df.empty:
    st.warning("No player data available. Check your API key or try again later.")
else:
    # Sidebar filters
    st.sidebar.header("Filters")
    selected_region = st.sidebar.selectbox("Select Region", ["All Regions"] + sorted(df["Region"].unique()))
    selected_team = st.sidebar.selectbox("Select Team", ["All Teams"] + sorted(df["Team"].unique()))
    selected_position = st.sidebar.selectbox("Select Position", ["All Positions"] + sorted(df["Position"].dropna().unique()))

    # Seeding segment filter
    seeding_options = {
        "All Seeds": None,
        "1-4": (1, 4),
        "5-8": (5, 8),
        "9-12": (9, 12),
        "13-16": (13, 16)
    }
    selected_seeding_segment = st.sidebar.selectbox("Select Seeding Segment", list(seeding_options.keys()))

    # Apply filters
    filtered_df = df.copy()
    if selected_region != "All Regions":
        filtered_df = filtered_df[filtered_df["Region"] == selected_region]
    if selected_team != "All Teams":
        filtered_df = filtered_df[filtered_df["Team"] == selected_team]
    if selected_position != "All Positions":
        filtered_df = filtered_df[filtered_df["Position"] == selected_position]
    if selected_seeding_segment != "All Seeds":
        seed_range = seeding_options[selected_seeding_segment]
        filtered_df = filtered_df[(filtered_df["Seed"] >= seed_range[0]) & (filtered_df["Seed"] <= seed_range[1])]

    # Add a column for team rankings from net_rankings
    filtered_df['Rank'] = filtered_df['Team'].map(team_rankings)

    # Display player statistics
    st.write("### Player Statistics")
    st.dataframe(
        filtered_df[["Player", "Team", "Region", "Seed", "Position", "Points", "PPG", "FG%", "3P%", "Rank"]],
        column_config={
            "PPG": st.column_config.NumberColumn(format="%.1f"),
            "FG%": st.column_config.NumberColumn(format="%.1f"),
            "3P%": st.column_config.NumberColumn(format="%.1f"),
            "Rank": st.column_config.NumberColumn(format="%.0f")
        },
        hide_index=True,
        use_container_width=True
    )

    # Display team rankings in a separate column if using top 16 data
    if not use_tournament_data:
        st.write("### Current Rankings")
        team_rankings_df = pd.DataFrame(team_rankings.items(), columns=["Team", "Rank"])
        st.dataframe(team_rankings_df, hide_index=True, use_container_width=True)
