# import streamlit as st
# from data_loader import load_tournament_data
#
# st.set_page_config(layout="centered", page_title="Home Page", page_icon="🏠")
#
# st.title("🏀 March Madness Player Statistics")
# st.markdown("### NCAA Tournament Player Performance")
#
# df = load_tournament_data()
#
# if not df.empty:
#     st.sidebar.header("Filters")
#
#     # Team Filter
#     selected_team = st.sidebar.selectbox("Select Team", ["All Teams"] + sorted(df["Team"].unique()))
#
#     # Position Filter
#     selected_position = st.sidebar.selectbox("Select Position", ["All Positions"] + sorted(df["Position"].dropna().unique()))
#
#     # Seeding Segment Filter
#     seeding_options = {
#         "All Seeds": None,
#         "1-4": (1, 4),
#         "5-8": (5, 8),
#         "9-12": (9, 12),
#         "13-16": (13, 16)
#     }
#     selected_seeding_segment = st.sidebar.selectbox("Select Seeding Segment", list(seeding_options.keys()))
#
#     # Apply Filters
#     filtered_df = df.copy()
#
#     if selected_team != "All Teams":
#         filtered_df = filtered_df[filtered_df["Team"] == selected_team]
#
#     if selected_position != "All Positions":
#         filtered_df = filtered_df[filtered_df["Position"] == selected_position]
#
#     if selected_seeding_segment != "All Seeds":
#         seed_range = seeding_options[selected_seeding_segment]
#         filtered_df = filtered_df[(filtered_df["Seed"] >= seed_range[0]) & (filtered_df["Seed"] <= seed_range[1])]
#
#     # Display Filtered Player Statistics
#     st.write("### Player Statistics")
#     st.dataframe(
#         filtered_df,
#         column_config={
#             "PPG": st.column_config.NumberColumn(format="%.1f"),
#             "FG%": st.column_config.NumberColumn(format="%.1f"),
#             "3P%": st.column_config.NumberColumn(format="%.1f")
#         },
#         hide_index=True,
#         use_container_width=True,
#         height=600
#     )
#
#     # Tournament Leaders
#     if not filtered_df.empty:
#         st.subheader("Tournament Leaders")
#         cols = st.columns(2)
#         with cols[0]:
#             st.metric("Top Scorer", filtered_df.iloc[0]['Points'], filtered_df.iloc[0]['Player'])
#         with cols[1]:
#             ppg_leader = filtered_df.loc[filtered_df['PPG'].idxmax()]
#             st.metric("PPG Leader", ppg_leader['PPG'], ppg_leader['Player'])
#     else:
#         st.warning("No data available for the selected filters.")
#
# else:
#     st.warning("No player data available. Check your API key or try again later.")


import streamlit as st
import pandas as pd
from data_loader import load_tournament_data

st.set_page_config(layout="centered", page_title="Home Page", page_icon="🏠")
st.title("🏀 March Madness Player Statistics")
st.markdown("### NCAA Tournament Player Performance")

df = load_tournament_data()

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
    st.write("### Player Statistics")
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
