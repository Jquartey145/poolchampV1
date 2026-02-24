import streamlit as st
import stripe
import pandas as pd
from data_loader import load_regular_season_data
from firebase_util import save_submission, db
from navigation import render_navigation

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


# ── Firestore helpers for pending submissions ─────────────────────────────────

def save_pending_to_firestore(stripe_session_id: str, team_data: dict):
    """Save team data to Firestore under pending_submissions/{stripe_session_id}."""
    db.collection("pending_submissions").document(stripe_session_id).set(team_data)


def get_pending_from_firestore(stripe_session_id: str):
    """Retrieve pending team data from Firestore by Stripe session ID."""
    doc = db.collection("pending_submissions").document(stripe_session_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def delete_pending_from_firestore(stripe_session_id: str):
    """Clean up the pending submission after it's been finalized."""
    db.collection("pending_submissions").document(stripe_session_id).delete()


# ── Core functions ────────────────────────────────────────────────────────────

def get_checkout_page_url():
    app_url = st.secrets.get("APP_URL", "http://localhost:8501/BuildYourTeam")
    return app_url.replace("/BuildYourTeam", "/Checkout")


def create_stripe_session(team_info: dict):
    """Create a Stripe Checkout Session."""
    checkout_page_url = get_checkout_page_url()
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
    """
    Verify payment with Stripe, retrieve team data from Firestore,
    finalize the submission, and clean up the pending record.
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status != "paid":
            return False, None

        # Retrieve team data from Firestore (survives the Stripe redirect)
        pending = get_pending_from_firestore(session_id)
        if not pending:
            st.error("Team data not found. Please contact support with your Stripe session ID: " + session_id)
            return False, None

        # Compute total points
        df = load_regular_season_data()
        if isinstance(df, list):
            df = pd.DataFrame(df)
        selected_names = [p["name"] for p in pending.get("players", [])]
        pending["total_points"] = int(df[df["Player"].isin(selected_names)]["Points"].sum())

        # Finalize fields
        pending["payment_type"] = "Stripe"
        pending["stripe_session_id"] = session_id
        pending["payment_status"] = "paid"

        # Save as official submission
        save_submission(pending)

        # Clean up pending record
        delete_pending_from_firestore(session_id)

        st.session_state.submission_saved = True
        st.session_state.pending_submission = None
        return True, pending["team_name"]

    except stripe.error.StripeError as e:
        st.error(f"Stripe error: {e.user_message}")
        return False, None


# ── Page routing ──────────────────────────────────────────────────────────────

params = st.query_params
payment_status = params.get("payment", None)
session_id_param = params.get("session_id", None)

# ── Returning from Stripe: success ───────────────────────────────────────────
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
            st.error("We couldn't verify your payment. Please contact support.")
            st.caption(f"Reference ID: `{session_id_param}`")
            st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")

# ── Returning from Stripe: cancelled ─────────────────────────────────────────
elif payment_status == "cancelled":
    st.query_params.clear()
    st.title("❌ Payment Cancelled")
    st.warning("Your payment was cancelled. Your team has not been submitted.")
    st.page_link("pages/BuildYourTeam.py", label="← Go back and try again")

# ── No pending submission (navigated here directly) ───────────────────────────
elif not st.session_state.pending_submission:
    st.title("💳 Checkout")
    st.warning("No team data found. Please go back and fill out your team details first.")
    st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")

# ── Normal flow: create Stripe session, save to Firestore, show pay button ────
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
        # Create Stripe session
        checkout_session = create_stripe_session(pending)

        # Save team data to Firestore keyed by Stripe session ID
        # This ensures data survives the external Stripe redirect
        save_pending_to_firestore(checkout_session.id, pending)

        st.link_button(
            "💳 Pay $25.00 with Stripe",
            checkout_session.url,
            use_container_width=True,
            type="primary"
        )
        st.markdown("")
        st.page_link("pages/BuildYourTeam.py", label="← Cancel and go back")

    except Exception as e:
        st.error(f"Failed to create payment session: {str(e)}")
        st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")