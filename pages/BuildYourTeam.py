import streamlit as st
import pandas as pd
import datetime
import pytz
import stripe
import json
from data_loader import load_regular_season_data
from firebase_util import save_submission
from navigation import render_navigation

render_navigation()

# ── Stripe config ────────────────────────────────────────────────────────────
stripe.api_key = st.secrets.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = st.secrets.get("STRIPE_PUBLISHABLE_KEY", "")
ENTRY_FEE_CENTS = 2500  # $25.00

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
if "payment_verified" not in st.session_state:
    st.session_state.payment_verified = False
if "stripe_session_id" not in st.session_state:
    st.session_state.stripe_session_id = None
if "pending_submission" not in st.session_state:
    st.session_state.pending_submission = None
if "submission_saved" not in st.session_state:
    st.session_state.submission_saved = False


# ── Stripe helpers ────────────────────────────────────────────────────────────

def create_checkout_session(team_info: dict, success_url: str, cancel_url: str):
    """Create a Stripe Checkout Session and return the URL."""
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "March Madness Entry Fee",
                    "description": f"Team: {team_info['team_name']} — {team_info['participant']}",
                },
                "unit_amount": ENTRY_FEE_CENTS,
            },
            "quantity": 1,
        }],
        mode="payment",
        customer_email=team_info.get("email_address"),
        metadata={
            "team_name": team_info["team_name"],
            "participant": team_info["participant"],
        },
        success_url=success_url + "?payment=success&session_id={CHECKOUT_SESSION_ID}",
        cancel_url=cancel_url + "?payment=cancelled",
    )
    return session


def verify_stripe_session(session_id: str):
    """Retrieve the Stripe session and confirm payment succeeded."""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return session.payment_status == "paid", session
    except stripe.error.StripeError as e:
        st.error(f"Stripe error: {e.user_message}")
        return False, None


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
       - Enter your team name and info, pay the $25 entry fee via Stripe, and good luck!
    4. **Key Dates**:
        - Selection Sunday: 3/16
        - First Four/Play-in Games: 3/18 - 3/19
        - 1st and 2nd rounds: 3/20 – 3/23
        - Sweet 16 and Elite 8: 3/27-3/30
        - Final Four: 4/5
        - National Championship: 4/7
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

    ppg_mapping = {}
    team_mapping = {}
    for player in players:
        try:
            ppg_mapping[player] = seed_df.loc[seed_df["Player"] == player, "PPG"].iloc[0]
            team_mapping[player] = seed_df.loc[seed_df["Player"] == player, "Team"].iloc[0]
        except IndexError:
            ppg_mapping[player] = 0
            team_mapping[player] = "Unknown"

    for i in range(3):
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
                else f"{option} / {team_mapping.get(option, 'Unknown')} (PPG: {ppg_mapping.get(option, 0):.1f})"
        )
        if selection != "Select a player":
            player_data = seed_df.loc[seed_df["Player"] == selection].iloc[0]
            st.session_state.selected_players[seed_range][i] = {
                "name": selection,
                "team": player_data["Team"],
                "seed": int(player_data["Seed"]),
                "position": player_data["Position"]
            }
        else:
            st.session_state.selected_players[seed_range][i] = ""


def review_team_tab():
    st.header("📊 Review Your Team")
    all_selected = [p for players in st.session_state.selected_players.values()
                    for p in players if p and isinstance(p, dict)]
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

    all_selected = [p for players in st.session_state.selected_players.values()
                    for p in players if p and isinstance(p, dict)]
    if len(all_selected) != 12:
        st.error("You must select exactly 12 players (3 from each seed bracket).")
        return

    # ── Check for returning Stripe redirect ──────────────────────────────────
    params = st.query_params
    payment_status = params.get("payment", None)
    session_id_param = params.get("session_id", None)

    if payment_status == "success" and session_id_param and not st.session_state.submission_saved:
        with st.spinner("Verifying payment with Stripe..."):
            paid, stripe_session = verify_stripe_session(session_id_param)

        if paid:
            st.session_state.payment_verified = True
            st.session_state.stripe_session_id = session_id_param

            # Retrieve the pending submission stored before redirect
            pending = st.session_state.get("pending_submission")
            if pending:
                pending["payment_type"] = "Stripe"
                pending["stripe_session_id"] = session_id_param
                pending["payment_status"] = "paid"

                df = load_regular_season_data()
                if isinstance(df, list):
                    df = pd.DataFrame(df)
                selected_names = [p["name"] for p in pending["players"]]
                pending["total_points"] = int(df[df["Player"].isin(selected_names)]["Points"].sum())

                save_submission(pending)
                st.session_state.submission_saved = True
                st.session_state.pending_submission = None

                # Clear query params so a refresh doesn't re-submit
                st.query_params.clear()

                st.success(f"🎉 Payment confirmed! Team **'{pending['team_name']}'** submitted successfully!")
                st.balloons()
                return
            else:
                st.warning("Payment verified but team info was lost. Please re-submit your team details below.")
                st.query_params.clear()

        else:
            st.error("⚠️ Payment could not be verified. Please try again.")
            st.query_params.clear()

    elif payment_status == "cancelled":
        st.warning("Payment was cancelled. Please complete payment to submit your team.")
        st.query_params.clear()

    # ── If already saved this session, show success ───────────────────────────
    if st.session_state.submission_saved:
        st.success("✅ Your team has already been submitted and payment confirmed!")
        return

    # ── Team submission form ──────────────────────────────────────────────────
    st.info("💳 A **$25 entry fee** is required to submit your team. You'll be redirected to Stripe to complete payment.")

    with st.form("team_submission"):
        st.subheader("🏀 Team Information")
        team_name = st.text_input("Team Name", placeholder="Enter your team name")

        st.subheader("👤 Participant Information")
        first_name = st.text_input("First Name", placeholder="Enter your first name")
        last_name = st.text_input("Last Name", placeholder="Enter your last name")
        email = st.text_input("Email Address", placeholder="Enter your email address")

        st.subheader("💳 Payment")
        st.write("You will be redirected to Stripe's secure checkout to pay the **$25 entry fee**. Your team will only be submitted after successful payment.")

        submitted = st.form_submit_button("Proceed to Payment →")

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
                # Store team data in session before redirecting to Stripe
                submission_data = {
                    "team_name": team_name,
                    "participant": f"{first_name} {last_name}",
                    "email_address": email,
                    "players": all_selected,
                    "total_points": 0,  # will be computed after payment
                }
                st.session_state.pending_submission = submission_data

                # Build success/cancel URLs pointing back to this page
                try:
                    app_url = st.secrets.get("APP_URL", "http://localhost:8501/BuildYourTeam")
                    checkout_session = create_checkout_session(
                        team_info=submission_data,
                        success_url=app_url,
                        cancel_url=app_url,
                    )
                    checkout_url = checkout_session.url
                    # Use JS redirect + prominent fallback button
                    st.markdown(
                        f"""
                        <script>window.location.href = "{checkout_url}";</script>
                        <div style="text-align:center; margin-top: 2rem;">
                            <p style="font-size:1.1rem;">Redirecting you to Stripe secure checkout...</p>
                            <a href="{checkout_url}" target="_self"
                               style="display:inline-block; background-color:#635BFF; color:white;
                                      padding:14px 32px; border-radius:6px; font-size:1.1rem;
                                      font-weight:600; text-decoration:none; margin-top:1rem;">
                                💳 Click here to pay $25.00
                            </a>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                except Exception as e:
                    st.error(f"Failed to create payment session: {str(e)}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    st.title("🏀 March Madness Team Builder")
    ct = pytz.timezone("America/Chicago")
    now_ct = datetime.datetime.now(ct)
    naive_deadline = datetime.datetime(2025, 3, 20, 11, 0)
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