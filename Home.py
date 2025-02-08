import streamlit as st
from data_loader import load_tournament_data

st.set_page_config(layout="centered",page_title="Home Page", page_icon="🏠")

st.title("🏀 March Madness Player Statistics")
st.markdown("### NCAA Tournament Player Performance")

df = load_tournament_data()

if not df.empty:
    st.sidebar.header("Filters")
    selected_team = st.sidebar.selectbox("Select Team", ["All Teams"] + sorted(df["Team"].unique()))
    selected_position = st.sidebar.selectbox("Select Position", ["All Positions"] + sorted(df["Position"].dropna().unique()))

    filtered_df = df.copy()
    if selected_team != "All Teams":
        filtered_df = filtered_df[filtered_df["Team"] == selected_team]
    if selected_position != "All Positions":
        filtered_df = filtered_df[filtered_df["Position"] == selected_position]

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

    st.subheader("Tournament Leaders")
    cols = st.columns(2)
    with cols[0]:
        st.metric("Top Scorer", filtered_df.iloc[0]['Points'], filtered_df.iloc[0]['Player'])
    with cols[1]:
        ppg_leader = filtered_df.loc[filtered_df['PPG'].idxmax()]
        st.metric("PPG Leader", ppg_leader['PPG'], ppg_leader['Player'])
else:
    st.warning("No player data available. Check your API key or try again later.")