import streamlit as st
import pandas as pd
from data_loader import load_top16_player_data
from firebase_util import save_submission
from navigation import render_navigation

render_navigation()

# Initialize session state
if "selected_players" not in st.session_state:
    st.session_state.selected_players = {
        "1-4": [],
        "5-8": [],
        "9-12": [],
        "13-16": []
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
       - 3 players must come from each seeding segment.
       - Each player's points will contribute to your team’s total score.
       - No substitutions if a play-in player loses.
       - Prizes for the top four teams.
    2. **Review Your Team**:
       - Review your team’s selected players and stats.
    3. **Submit Your Team**:
       - Enter your team name, submit, and good luck!
    """)

def seed_selection_tab(seed_range):
    st.header(f"🌱 Seed {seed_range}")
    df = load_top16_player_data()
    if isinstance(df, list):
        df = pd.DataFrame(df)
    if df.empty:
        st.warning("No player data available. Check your API key or try again later.")
        return
    # Ensure exactly 3 players stored for this seed range
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
        # Create a set of already selected player names (for this seed group)
        others = {p["name"] for j, p in enumerate(st.session_state.selected_players[seed_range])
                  if j != i and p != "" and isinstance(p, dict)}
        available_options = ["Select a player"] + [p for p in players if p not in others]
        current_selection = st.session_state.selected_players[seed_range][i]
        if not (isinstance(current_selection, dict) and current_selection.get("name") in available_options):
            current_selection = "Select a player"
        else:
            current_selection = current_selection["name"]
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
            # Lookup the player's row in seed_df and store an object with details.
            player_data = seed_df.loc[seed_df["Player"] == selection].iloc[0]
            st.session_state.selected_players[seed_range][i] = {
                "name": selection,
                "team": player_data["Team"],
                "seed": int(player_data["Seed"]),  # Convert numpy.int64 to int
                "position": player_data["Position"]
            }
        else:
            st.session_state.selected_players[seed_range][i] = ""

def review_team_tab():
    st.header("📊 Review Your Team")
    # Flatten selected players (only include objects/dictionaries)
    all_selected = [p for players in st.session_state.selected_players.values() for p in players if p and isinstance(p, dict)]
    if not all_selected:
        st.warning("No players selected yet! Visit the seed tabs to build your team.")
        return
    selected_df = pd.DataFrame(all_selected)
    st.write(f"**Total Players Selected**: {len(selected_df)}")
    df = load_top16_player_data()
    if isinstance(df, list):
        df = pd.DataFrame(df)
    selected_names = selected_df["name"].tolist()
    team_df = df[df["Player"].isin(selected_names)]
    st.write(f"**Total Points**: {team_df['Points'].sum()}")
    st.write(f"**Average PPG**: {team_df['PPG'].mean():.1f}")
    st.dataframe(
        selected_df[["name", "position", "team", "seed"]],
        column_config={"seed": st.column_config.NumberColumn(format="%.0f")},
        hide_index=True,
        use_container_width=True
    )

def submit_team_tab():
    st.header("✅ Submit Your Team")
    # Flatten selected players; ensure they are valid objects/dictionaries
    all_selected = [p for players in st.session_state.selected_players.values() for p in players if p and isinstance(p, dict)]
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
        payment_type = st.selectbox("Payment Type", ["Venmo"])
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
                df = load_top16_player_data()
                if isinstance(df, list):
                    df = pd.DataFrame(df)
                selected_names = [p["name"] for p in all_selected]
                total_points = int(df[df["Player"].isin(selected_names)]["Points"].sum())
                submission = {
                    "team_name": team_name,
                    "participant": f"{first_name} {last_name}",
                    "payment_type": payment_type,
                    "players": all_selected,  # Detailed player objects with native types
                    "total_points": total_points
                }
                # Upload the detailed submission data to Firestore
                save_submission(submission)
                st.success(f"Team '{team_name}' submitted successfully!")

if __name__ == "__main__":
    main()
