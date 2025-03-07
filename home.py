import streamlit as st
import pandas as pd
from data_loader import load_top16_player_data, load_net_rankings
from navigation import render_navigation

render_navigation()

st.title("🏀 Marci's Madness Player Statistics")
st.markdown("### NCAA Current Player Performance - Top 16 Teams")

# Load player data
data = load_top16_player_data()
df = pd.DataFrame(data)
df = df.drop('Team_ID', axis=1)

# Load net rankings
net_rankings = load_net_rankings()
if not net_rankings:
    st.warning("Unable to load NET rankings.")
    net_rankings = {"top16": []}  # Fallback in case data is not available

# Create a dictionary to map team names to their net rankings
team_rankings = {team["team_name"]: team["rank"] for team in net_rankings.get("top16", [])}

if df.empty:
    st.warning("bruh")

if not df.empty:
    st.sidebar.header("Filters")
    selected_team = st.sidebar.selectbox("Select Team", ["All Teams"] + sorted(df["Team"].unique()))
    selected_position = st.sidebar.selectbox("Select Position", ["All Positions"] + sorted(df["Position"].dropna().unique()))
    seeding_options = {
        "All Seeds": None,
        "1-4": (1, 4),
        "5-8": (5, 8),
        "9-12": (9, 12),
        "13-16": (13, 16)
    }
    selected_seeding_segment = st.sidebar.selectbox("Select Seeding Segment", list(seeding_options.keys()))
    filtered_df = df.copy()
    if selected_team != "All Teams":
        filtered_df = filtered_df[filtered_df["Team"] == selected_team]
    if selected_position != "All Positions":
        filtered_df = filtered_df[filtered_df["Position"] == selected_position]
    if selected_seeding_segment != "All Seeds":
        seed_range = seeding_options[selected_seeding_segment]
        filtered_df = filtered_df[(filtered_df["Seed"] >= seed_range[0]) & (filtered_df["Seed"] <= seed_range[1])]

    # Add a column for team rankings from net_rankings
    filtered_df['Seed'] = filtered_df['Team'].map(team_rankings)

    col1, col2 = st.columns([3, 2])  # Slightly larger left column (for player stats) and right column (for team rankings)

    with col1:
        st.write("### Player Statistics (Top 16 Teams)")
        st.dataframe(
            filtered_df,
            column_config={
                "PPG": st.column_config.NumberColumn(format="%.1f"),
                "FG%": st.column_config.NumberColumn(format="%.1f"),
                "3P%": st.column_config.NumberColumn(format="%.1f")
            },
            hide_index=True
             )

    with col2:
        # Display the team rankings in the second column
        team_rankings_df = pd.DataFrame(team_rankings.items(), columns=["Team", "Rank"])
        st.write("### Current Rankings")
        st.dataframe(team_rankings_df, hide_index=True)

    if not filtered_df.empty:
        st.subheader("Tournament Leaders")
        cols = st.columns(2)
        with cols[0]:
            st.metric("Top Scorer", filtered_df.iloc[0]['Points'], filtered_df.iloc[0]['Player'])
        with cols[1]:
            ppg_leader = filtered_df.loc[filtered_df['PPG'].idxmax()]
            st.metric("PPG Leader", ppg_leader['PPG'], ppg_leader['Player'])
    else:
        st.warning("No data available for the selected filters.")
else:
    st.warning("No player data available. Check your API key or try again later.")
