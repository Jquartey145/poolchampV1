import streamlit as st
import pandas as pd
from data_loader import load_tournament_data
from firebase_util import save_submission

# Initialize session state for selected players
if "selected_players" not in st.session_state:
    st.session_state.selected_players = {
        "1-4": ["", "", ""],
        "5-8": ["", "", ""],
        "9-12": ["", "", ""],
        "13-16": ["", "", ""]
    }
if "submissions" not in st.session_state:
    st.session_state.submissions = []

def main():
    st.title("🏀 March Madness Team Builder")
    tab_names = [
        "Rules", "Seed 1-4", "Seed 5-8", "Seed 9-12",
        "Seed 13-16", "Review Team", "Submit Team"
    ]
    tabs = st.tabs(tab_names)
    with tabs[0]:
        rules_tab()
    with tabs[1]:
        seed_selection_tab("1-4")
    with tabs[2]:
        seed_selection_tab("5-8")
    with tabs[3]:
        seed_selection_tab("9-12")
    with tabs[4]:
        seed_selection_tab("13-16")
    with tabs[5]:
        review_team_tab()
    with tabs[6]:
        submit_team_tab()

def rules_tab():
    st.header("📜 Rules")
    st.write("""
    ### How to Build Your Team:
    1. **Select Players**:
       - Choose your team, which will comprise of 12 players.
       - Of the 12 players selected, 3 must come from each bracket seeding segment.
       - Each player’s individual points throughout the tournament (will not include play-in games) will be added to your team’s total.
       - After each round, updated standings will be posted.
       - If you choose a player who participates within a “Play-in Game,” their point totals will begin to accumulate in their First-Round matchup. If you choose them and they lose their play-in game, there won’t be an opportunity to substitute players.
       - Prizes will be paid out to the top four teams (“Final 4”) at the conclusion of the tournament.
       - In lieu of a tie (each team having the same players), payouts will be adjusted accordingly.
       - **Note:** You cannot select the same player more than once.
    2. **Review Your Team**:
       - Review your team here to see your selected players and their stats.
    3. **Submit Your Team**:
       - Enter a team name, submit your team, and good luck!
    """)

def seed_selection_tab(seed_range):
    st.header(f"🌱 Seed {seed_range}")
    df = load_tournament_data()
    if df.empty:
        st.warning("No player data available. Check your API key or try again later.")
        return
    if len(st.session_state.selected_players[seed_range]) < 3:
        st.session_state.selected_players[seed_range] = ["", "", ""]
    start, end = map(int, seed_range.split("-"))
    seed_df = df[df["Seed"].between(start, end)]
    players = seed_df["Player"].unique().tolist()
    ppg_mapping = {}
    for player in players:
        try:
            ppg_value = seed_df.loc[seed_df["Player"] == player, "PPG"].iloc[0]
        except IndexError:
            ppg_value = 0
        ppg_mapping[player] = ppg_value
    for i in range(3):
        others = {
            st.session_state.selected_players[seed_range][j]
            for j in range(3)
            if j != i and st.session_state.selected_players[seed_range][j] != ""
        }
        available_options = ["Select a player"] + [p for p in players if p not in others]
        current_selection = st.session_state.selected_players[seed_range][i]
        if current_selection not in available_options:
            current_selection = "Select a player"
        default_index = available_options.index(current_selection)
        selection = st.selectbox(
            f"Player {i+1}",
            available_options,
            key=f"{seed_range}_player_{i}",
            index=default_index,
            format_func=lambda option: option if option == "Select a player"
                else f"{option} (PPG: {ppg_mapping.get(option, 0):.1f})"
        )
        if selection != "Select a player":
            st.session_state.selected_players[seed_range][i] = selection
        else:
            st.session_state.selected_players[seed_range][i] = ""

def review_team_tab():
    st.header("📊 Review Your Team")
    df = load_tournament_data()
    all_selected = [
        player for players in st.session_state.selected_players.values() for player in players if player
    ]
    if not all_selected:
        st.warning("No players selected yet! Visit the seed tabs to build your team.")
        return
    team_df = df[df["Player"].isin(all_selected)]
    st.write(f"**Total Players Selected**: {len(team_df)}")
    st.write(f"**Total Points**: {team_df['Points'].sum()}")
    st.write(f"**Average PPG**: {team_df['PPG'].mean():.1f}")
    st.dataframe(
        team_df[["Player", "Team", "Seed", "Points", "PPG"]],
        column_config={
            "PPG": st.column_config.NumberColumn(format="%.1f"),
            "Points": st.column_config.NumberColumn(format="%.0f")
        },
        hide_index=True,
        use_container_width=True
    )

def submit_team_tab():
    st.header("✅ Submit Your Team")
    all_selected = [
        player for players in st.session_state.selected_players.values() for player in players if player
    ]
    if len(all_selected) != 12:
        st.error("You must select exactly 12 players (3 from each seed bracket).")
        return
    with st.form("team_submission"):
        st.subheader("🏀 Team Information")
        team_name = st.text_input("Team Name", placeholder="Enter your team name")
        st.subheader("👤 Participant Information")
        first_name = st.text_input("First Name", placeholder="Enter your first name")
        last_name = st.text_input("Last Name", placeholder="Enter your last name")
        st.subheader("💳 Payment Information")
        payment_type = st.selectbox("Payment Type", ["Credit Card", "PayPal", "Venmo", "Cash"])
        submitted = st.form_submit_button("Submit Team")
        if submitted:
            if not team_name:
                st.error("Please enter a team name.")
            elif not first_name:
                st.error("Please enter your first name.")
            elif not last_name:
                st.error("Please enter your last name.")
            elif not payment_type:
                st.error("Please select a payment type.")
            else:
                df = pd.DataFrame(load_tournament_data())
                total_points = int(df[df["Player"].isin(all_selected)]["Points"].sum())
                submission = {
                    "team_name": team_name,
                    "participant": f"{first_name} {last_name}",
                    "payment_type": payment_type,
                    "players": all_selected,
                    "total_points": total_points
                }
                save_submission(submission)
                st.success(f"Team '{team_name}' submitted successfully!")

if __name__ == "__main__":
    main()
