import streamlit as st
import pandas as pd
import braintree
import streamlit.components.v1 as components
from data_loader import load_regular_season_data
from firebase_util import save_submission
from navigation import render_navigation

st.set_page_config(page_title="Checkout", page_icon="💳")
render_navigation()

ENTRY_FEE_DOLLARS = "25.00"

# ── Session state defaults ────────────────────────────────────────────────────
if "submission_saved" not in st.session_state:
    st.session_state.submission_saved = False
if "pending_submission" not in st.session_state:
    st.session_state.pending_submission = None


# ── Braintree gateway ─────────────────────────────────────────────────────────
@st.cache_resource
def get_gateway():
    return braintree.BraintreeGateway(
        braintree.Configuration(
            environment=braintree.Environment.Sandbox,  # swap to Sandbox for testing
            merchant_id=st.secrets["BRAINTREE_MERCHANT_ID"],
            public_key=st.secrets["BRAINTREE_PUBLIC_KEY"],
            private_key=st.secrets["BRAINTREE_PRIVATE_KEY"],
        )
    )


def generate_client_token() -> str:
    gateway = get_gateway()
    return gateway.client_token.generate({})


def charge_nonce(nonce: str, amount: str) -> tuple[bool, str]:
    """Submit payment nonce to Braintree. Returns (success, transaction_id_or_error)."""
    gateway = get_gateway()
    result = gateway.transaction.sale({
        "amount": amount,
        "payment_method_nonce": nonce,
        "options": {"submit_for_settlement": True},
    })
    if result.is_success:
        return True, result.transaction.id
    else:
        msg = "; ".join(e.message for e in result.errors.deep_errors)
        return False, msg


# ── Finalize submission ───────────────────────────────────────────────────────
def finalize_submission(pending: dict, transaction_id: str) -> str:
    df = load_regular_season_data()
    if isinstance(df, list):
        df = pd.DataFrame(df)

    selected_names = [p["name"] for p in pending.get("players", [])]
    pending["total_points"] = int(df[df["Player"].isin(selected_names)]["Points"].sum())
    pending["payment_type"] = "Venmo"
    pending["payment_status"] = "paid"
    pending["transaction_id"] = transaction_id

    import uuid
    doc_id = str(uuid.uuid4())
    save_submission(pending, doc_id=doc_id)

    st.session_state.submission_saved = True
    st.session_state.pending_submission = None
    return pending["team_name"]


# ── Drop-in UI HTML ───────────────────────────────────────────────────────────
def dropin_html(client_token: str) -> str:
    """
    Renders the Braintree Drop-in UI with Venmo prioritised.
    On submit, the nonce is bridged back to Streamlit via a query param
    (postMessage → parent URL update → Streamlit rerun).
    """
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <script src="https://js.braintreegateway.com/web/dropin/1.43.0/js/dropin.min.js"></script>
      <style>
        body {{
          font-family: sans-serif;
          margin: 0;
          padding: 12px;
          background: transparent;
        }}
        #submit-btn {{
          margin-top: 16px;
          width: 100%;
          padding: 14px;
          background: #008CFF;
          color: white;
          font-size: 16px;
          font-weight: 600;
          border: none;
          border-radius: 8px;
          cursor: pointer;
        }}
        #submit-btn:disabled {{
          opacity: 0.5;
          cursor: not-allowed;
        }}
        #status {{
          margin-top: 12px;
          font-size: 14px;
          color: #444;
          text-align: center;
        }}
      </style>
    </head>
    <body>
      <div id="dropin-container"></div>
      <button id="submit-btn" disabled>Pay $25.00 with Venmo</button>
      <div id="status"></div>

      <script>
        braintree.dropin.create({{
          authorization: "{client_token}",
          container: "#dropin-container",
          venmo: {{
            allowNewBrowserTab: false
          }},
          paymentOptionPriority: ["venmo", "card"]
        }}, function(err, instance) {{
          if (err) {{
            document.getElementById("status").innerText = "Error loading payment form: " + err.message;
            return;
          }}

          var btn = document.getElementById("submit-btn");
          btn.disabled = false;

          btn.addEventListener("click", function() {{
            btn.disabled = true;
            document.getElementById("status").innerText = "Processing...";

            instance.requestPaymentMethod(function(err, payload) {{
              if (err) {{
                document.getElementById("status").innerText = "Payment error: " + err.message;
                btn.disabled = false;
                return;
              }}

              // Bridge nonce to Streamlit via query param
              var url = new URL(window.parent.location.href);
              url.searchParams.set("nonce", payload.nonce);
              window.parent.location.href = url.toString();
            }});
          }});
        }});
      </script>
    </body>
    </html>
    """


# ── Page routing ──────────────────────────────────────────────────────────────

if st.session_state.submission_saved:
    st.title("🎉 You're all set!")
    st.success("Your team has been submitted and payment confirmed!")
    st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")
    st.stop()

if not st.session_state.pending_submission:
    st.title("💳 Checkout")
    st.warning("No team data found. Please go back and fill out your team details first.")
    st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")
    st.stop()

# ── Check for nonce returned via query param (post Drop-in redirect) ──────────
params = st.query_params
nonce = params.get("nonce", None)

if nonce:
    st.query_params.clear()
    pending = st.session_state.pending_submission
    with st.spinner("Verifying payment with Braintree..."):
        success, result = charge_nonce(nonce, ENTRY_FEE_DOLLARS)
    if success:
        team_name = finalize_submission(pending, result)
        st.title("🎉 Payment Confirmed!")
        st.success(f"Team **'{team_name}'** has been submitted successfully!")
        st.balloons()
        st.rerun()
    else:
        st.title("⚠️ Payment Failed")
        st.error(f"Braintree error: {result}")
        st.caption("Please try again or contact support.")
        st.page_link("pages/BuildYourTeam.py", label="← Back to Team Builder")
    st.stop()

# ── Normal flow: show order summary + Drop-in UI ──────────────────────────────
pending = st.session_state.pending_submission

st.title("💳 Complete Your Entry")
st.markdown("### Order Summary")
st.markdown(f"**Team:** {pending['team_name']}")
st.markdown(f"**Participant:** {pending['participant']}")
st.markdown(f"**Email:** {pending['email_address']}")
st.markdown(f"**Players selected:** {len(pending['players'])}")
st.divider()
st.markdown("### Entry Fee: $25.00")
st.caption("Pay securely via Venmo (powered by Braintree).")

# Generate client token once per session
if "braintree_client_token" not in st.session_state:
    with st.spinner("Loading payment form..."):
        try:
            st.session_state.braintree_client_token = generate_client_token()
        except KeyError as e:
            st.error(f"Missing secret key: {e} — check your secrets.toml")
            st.stop()
        except braintree.exceptions.authentication_error.AuthenticationError:
            st.error("Braintree authentication failed — check your BRAINTREE_MERCHANT_ID, BRAINTREE_PUBLIC_KEY, and BRAINTREE_PRIVATE_KEY in secrets.toml")
            st.stop()
        except Exception as e:
            st.error(f"Failed to load payment form: {type(e).__name__}: {e}")
            st.stop()

# Render the Braintree Drop-in UI
components.html(
    dropin_html(st.session_state.braintree_client_token),
    height=460,
    scrolling=False,
)

st.markdown("")
st.page_link("pages/BuildYourTeam.py", label="← Cancel and go back")