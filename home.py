import streamlit as st
import pandas as pd
from data_loader import load_regular_season_data, update_daily_player_points
from navigation import render_navigation

st.set_page_config(layout="wide")
render_navigation()
st.title("🏀 NCAA Regular Season Player Statistics")

# Load regular season data
data = load_regular_season_data()
df = pd.DataFrame(data)

if df.empty:
    st.warning("No player data available. Check your API key or try again later.")
else:
    # Sidebar filters
    st.sidebar.header("Filters")

    # Region filter (if available in data)
    if "Region" in df.columns:
        selected_region = st.sidebar.selectbox("Select Region", ["All Regions"] + sorted(df["Region"].unique()))
    else:
        selected_region = "All Regions"

    selected_team = st.sidebar.selectbox("Select Team", ["All Teams"] + sorted(df["Team"].unique()))
    selected_position = st.sidebar.selectbox("Select Position", ["All Positions"] + sorted(df["Position"].dropna().unique()))

    # Seeding filter
    seeding_options = {
        "All Seeds": None,
        "1-4": (1, 4),
        "5-8": (5, 8),
        "9-12": (9, 12),
        "13-16": (13, 16)
    }
    selected_seeding = st.sidebar.selectbox("Select Seed Range", list(seeding_options.keys()))

    # Apply filters
    filtered_df = df.copy()
    if selected_region != "All Regions" and "Region" in df.columns:
        filtered_df = filtered_df[filtered_df["Region"] == selected_region]
    if selected_team != "All Teams":
        filtered_df = filtered_df[filtered_df["Team"] == selected_team]
    if selected_position != "All Positions":
        filtered_df = filtered_df[filtered_df["Position"] == selected_position]
    if selected_seeding != "All Seeds":
        seed_range = seeding_options[selected_seeding]
        filtered_df = filtered_df[(filtered_df["Seed"] >= seed_range[0]) & (filtered_df["Seed"] <= seed_range[1])]

    # Display configuration
    columns_to_display = ["Player", "Team", "Seed", "Position", "Points", "PPG", "FG%", "3P%"]
    if "Region" in df.columns:
        columns_to_display.insert(2, "Region")

    st.write("### Player Statistics")
    st.dataframe(
        filtered_df[columns_to_display],
        column_config={
            "PPG": st.column_config.NumberColumn(format="%.1f"),
            "FG%": st.column_config.NumberColumn(format="%.1f"),
            "3P%": st.column_config.NumberColumn(format="%.1f")
        },
        hide_index=True,
        use_container_width=True
    )

#     st.sidebar.header("Developer Tools")
#     test_date = st.sidebar.text_input("Enter date to process (YYYY-MM-DD)")
#     if st.sidebar.button("Process Daily Updates"):
#         if test_date:
#             with st.spinner(f"Processing updates for {test_date}..."):
#                 update_daily_player_points(test_date)
#             st.success(f"Daily updates processed for {test_date}")
#         else:
#             st.error("Please enter a valid date")