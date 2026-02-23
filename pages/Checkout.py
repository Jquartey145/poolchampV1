import streamlit as st
import stripe
from data_loader import load_regular_season_data
from firebase_util import save_submission
from navigation import render_navigation
import pandas as pd

st.set_page_config(page_title="Checkout", page_icon="💳")
render_navigation()

# ── Stripe config ─────────────────────────────────────────────────────────────
stripe.api_key = st.secrets.get("STRIPE_SECRET_KEY", "")
ENTRY_FEE_CENTS = 2500  # $25.00

# ── Session state defaults ────────────────────────────────────────────────────
if "submission_saved" not in st.session_state:
    st.session_state.submission_saved = False
if "pending_submission" not in st.session_state:
    st.session_state.pending_submission = None


def get_app_url():
    """Return the correct base URL depending on environment."""
    app_url = st.secrets.get("APP_URL", "")
    if app_url:
        return app_url
    # Fallback for local dev
    return "http://localhost:8501/BuildYourTeam"


def create_checkout_session(team_info: dict):
    """Create a Stripe Checkout Session and return it."""
    base_url = get_app_url()
    # Success/cancel both return to BuildYourTeam page; Checkout page handles verification via query params
    checkout_page_url = base_url.replace("/BuildYourTeam", "/Checkout")

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
        success_url=checkout_page_url + "?payment=success&session_id={CHECKOUT_SESSION_ID}",
        cancel_url=checkout_page_url + "?payment=cancelled",
    )
    return session


def verify_and_save(session_id: str):
    """Verify payment with Stripe and save submission to Firestore."""
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            pending = st.session_state.get("pending_submission")
            if pending:
                pending["payment_type"] = "Stripe"
                pending["stripe_session_id"] = session_id
                pending["payment_status"] = "paid"

                df = load_regular_season_data()
                if isinstance(df, list):
                    df = pd.DataFrame(df)
                selected_names = [p["name"] for p in pending["players"]]
                pending["total_points"] = int(df[df["Player"].isin(selected_names)]["Points"].sum())

                save_submission(pending)
                st.session_state.submission_saved = True
                st.session_state.pending_submission = None
                return True, pending["team_name"]
            else:
                return False, None
        else:
            return False, None
    except stripe.error.StripeError as e:
        st.error(f"Stripe error: {e.user_message}")
        return False, None


# ── Main page logic ───────────────────────────────────────────────────────────

params = st.query_params
payment_status = params.get("payment", None)
session_id_param = params.get("session_id", None)

# ── Returning from Stripe: success ────────────────────────────────────────────
if payment_status == "success" and session_id_param:
    st.query_params.clear()

    if st.session_state.submission_saved:
        st.title("🎉 You're all set!")
        st.success("Your team has already been submitted and payment confirmed!")
        st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")
    else:
        with st.spinner("Verifying payment with Stripe..."):
            success, team_name = verify_and_save(session_id_param)

        if success:
            st.title("🎉 Payment Confirmed!")
            st.success(f"Team **'{team_name}'** has been submitted successfully!")
            st.balloons()
            st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")
        else:
            st.title("⚠️ Payment Verification Failed")
            st.error("We couldn't verify your payment. Please try again or contact support.")
            st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")

# ── Returning from Stripe: cancelled ─────────────────────────────────────────
elif payment_status == "cancelled":
    st.query_params.clear()
    st.title("❌ Payment Cancelled")
    st.warning("Your payment was cancelled. Your team has not been submitted.")
    st.page_link("pages/BuildYourTeam.py", label="← Go back and try again")

# ── No pending submission (e.g. navigated here directly) ─────────────────────
elif not st.session_state.pending_submission:
    st.title("💳 Checkout")
    st.warning("No team data found. Please go back and fill out your team details first.")
    st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")

# ── Normal flow: show Stripe pay button ──────────────────────────────────────
else:
    pending = st.session_state.pending_submission
    st.title("💳 Complete Your Entry")

    st.markdown("### Order Summary")
    st.markdown(f"**Team:** {pending['team_name']}")
    st.markdown(f"**Participant:** {pending['participant']}")
    st.markdown(f"**Email:** {pending['email_address']}")
    st.markdown(f"**Players selected:** {len(pending['players'])}")
    st.divider()
    st.markdown("### Entry Fee: $25.00")
    st.caption("Secure payment powered by Stripe.")

    try:
        checkout_session = create_checkout_session(pending)
        st.link_button("💳 Pay $25.00 with Stripe", checkout_session.url, use_container_width=True, type="primary")
        st.markdown("")
        st.page_link("pages/BuildYourTeam.py", label="← Cancel and go back")
    except Exception as e:
        st.error(f"Failed to create payment session: {str(e)}")
        st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")