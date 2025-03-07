import streamlit as st

def render_navigation():
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.page_link("home.py", label="Home", icon="🏠")
    with col2:
        st.page_link("pages/🏀Build_Your_Team.py", label="🏀Build Your Team")
    with col3:
        st.page_link("pages/🏆Leaderboard.py", label="🏆Leaderboard")
