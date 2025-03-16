import streamlit as st

def render_navigation():
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        st.page_link("home.py", label="Home", icon="🏠")
    with col2:
        st.page_link("pages/BuildYourTeam.py", label="🏀Build Your Team")
    with col3:
        st.page_link("pages/Leaderboard.py", label="🏆Leaderboard")
    with col4:
        st.page_link("pages/TeamDashboard.py", label="🔍Team Dashboard")
