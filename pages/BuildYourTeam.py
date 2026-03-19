import streamlit as st
import pandas as pd
import datetime
import pytz
from data_loader import load_regular_season_data
from firebase_util import save_submission
from navigation import render_navigation

render_navigation()

# ── Session state ─────────────────────────────────────────────────────────────
if "selected_players" not in st.session_state:
    st.session_state.selected_players = {
        "1-4": [],
        "5-8": [],
        "9-12": [],
        "13-16": []
    }
if "submissions" not in st.session_state:
    st.session_state.submissions = []



# ── Tab helpers ───────────────────────────────────────────────────────────────

def rules_tab():
    st.header("📜 Rules")
    st.write("""
    ### How to Build Your Team:
    1. **Select Players**:
       - Choose your team, which will comprise of 12 players.
       - 3 players must come from each seeding segment
        - 3 players on teams seeded 1-4
        - 3 players on teams seeded 5-8
        - 3 players on teams seeded 9-12
        - 3 players on teams seeded 13-16
       - Each player's individual points throughout the tournament (will not include play-in games) will be added to your team's total
       - After each round, updated standings will be posted on the leaderboard
       - If you choose a player who participates within a "Play-in Game," their point totals will begin to accumulate in their First-Round matchup. If you choose them and they lose their play-in game, there won't be an opportunity to substitute players.
       - Prizes will be paid out to the top four teams ("Final 4") at the conclusion of the tournament.
       - In lieu of a tie (each team having the same players), payouts will be adjusted accordingly
    2. **Review Your Team**:
       - Review your team's selected players and stats.
    3. **Submit Your Team**:
       - Enter your team name, submit, and send $30 via Venmo. Good luck!
    4. **Key Dates**:
        - Selection Sunday: 3/15
        - First Four: 3/17 - 3/18
        - 1st and 2nd rounds: 3/19 – 3/22
        - Sweet 16 and Elite 8: 3/26 - 3/29
        - Final Four: 4/4
        - National Championship: 4/6
    """)


def seed_selection_tab(seed_range):
    st.header(f"🌱 Seed {seed_range}")
    df = load_regular_season_data()
    if isinstance(df, list):
        df = pd.DataFrame(df)
    if df.empty:
        st.warning("No player data available. Check your API key or try again later.")
        return

    if len(st.session_state.selected_players[seed_range]) < 3:
        st.session_state.selected_players[seed_range] = ["", "", ""]

    start, end = map(int, seed_range.split("-"))
    seed_df = df[df["Seed"].between(start, end)]
    players = seed_df["Player"].unique().tolist()

    ppg_mapping  = {}
    team_mapping = {}
    for player in players:
        try:
            ppg_mapping[player]  = seed_df.loc[seed_df["Player"] == player, "PPG"].iloc[0]
            team_mapping[player] = seed_df.loc[seed_df["Player"] == player, "Team"].iloc[0]
        except IndexError:
            ppg_mapping[player]  = 0
            team_mapping[player] = "Unknown"

    for i in range(3):
        others = {
            p["name"] for j, p in enumerate(st.session_state.selected_players[seed_range])
            if j != i and p != "" and isinstance(p, dict)
        }
        available_options  = ["Select a player"] + [p for p in players if p not in others]
        current_selection  = st.session_state.selected_players[seed_range][i]
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
                else f"{option} / {team_mapping.get(option, 'Unknown')} (PPG: {ppg_mapping.get(option, 0):.1f})"
        )
        if selection != "Select a player":
            player_data = seed_df.loc[seed_df["Player"] == selection].iloc[0]
            st.session_state.selected_players[seed_range][i] = {
                "name":     selection,
                "team":     player_data["Team"],
                "seed":     int(player_data["Seed"]),
                "position": player_data["Position"]
            }
        else:
            st.session_state.selected_players[seed_range][i] = ""


def review_team_tab():
    st.header("📊 Review Your Team")
    all_selected = [
        p for players in st.session_state.selected_players.values()
        for p in players if p and isinstance(p, dict)
    ]
    if not all_selected:
        st.warning("No players selected yet! Visit the seed tabs to build your team.")
        return
    selected_df = pd.DataFrame(all_selected)
    st.write(f"**Total Players Selected**: {len(selected_df)}")
    df = load_regular_season_data()
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

    all_selected = [
        p for players in st.session_state.selected_players.values()
        for p in players if p and isinstance(p, dict)
    ]
    if len(all_selected) != 12:
        st.error("You must select exactly 12 players (3 from each seed bracket).")
        return

    with st.form("team_submission"):
        st.subheader("🏀 Team Information")
        team_name = st.text_input("Team Name", placeholder="Enter your team name")

        st.subheader("👤 Participant Information")
        first_name = st.text_input("First Name", placeholder="Enter your first name")
        last_name  = st.text_input("Last Name",  placeholder="Enter your last name")
        email      = st.text_input("Email Address", placeholder="Enter your email address")

        st.subheader("💳 Payment Information")
        payment_type = st.selectbox("Payment Type", ["Venmo"])
        venmo_name   = st.text_input("Venmo Username (if applicable)", placeholder="@username")

        submitted = st.form_submit_button("Submit Team")

        if submitted:
            if not team_name:
                st.error("Please enter a team name.")
            elif not first_name:
                st.error("Please enter your first name.")
            elif not last_name:
                st.error("Please enter your last name.")
            elif not email:
                st.error("Please enter your email address.")
            else:
                df = load_regular_season_data()
                if isinstance(df, list):
                    df = pd.DataFrame(df)
                selected_names = [p["name"] for p in all_selected]
                total_points   = int(df[df["Player"].isin(selected_names)]["Points"].sum())

                submission = {
                    "team_name":      team_name,
                    "participant":    f"{first_name} {last_name}",
                    "email_address":  email,
                    "payment_type":   payment_type,
                    "venmo_username": venmo_name,
                    "players":        all_selected,
                    "total_points":   total_points,
                }
                save_submission(submission)
                st.success(f"Team '{team_name}' submitted successfully! Please send $30 via {payment_type}.")
                st.balloons()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("🏀 March Madness Team Builder")
    ct  = pytz.timezone("America/Chicago")
    now_ct = datetime.datetime.now(ct)

    # Submissions lock when Round 1 tips off — March 19 2026 at 11:00 AM CT
    naive_deadline = datetime.datetime(2026, 3, 19, 17, 30)
    deadline = ct.localize(naive_deadline)

    if now_ct > deadline:
        st.title("⛔ Submissions Closed")
        st.write("Submissions have locked as the tournament has started. Good luck!")
        st.stop()

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


if __name__ == "__main__":
    main()