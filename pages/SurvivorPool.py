import streamlit as st
from navigation import render_navigation

st.set_page_config(layout="wide")
render_navigation()

st.title("🛟 Survivor Pool")

st.markdown(
    """
    I know the majority of you are gambling degenerates 😊 – but please remember a portion of your entry ($5) will be donated to the **Marci Bikshorn Sarcoma Research Fund**,
    a fund dedicated to funding the ongoing and progressive research at *Washington University in St. Louis’ Siteman Cancer Center* under the direction of **Dr. Brian Van Tine**.
    \nFor those of you who aren’t aware, my mother, **Marci (Cherry) Bikshorn**, passed away from **leiomyosarcoma** in 2016.
    \nOn behalf of my family and many others affected by this disease, I want to take the time to personally thank you for your interest and/or continued participation in this pool.
    """
)

st.divider()

st.markdown("### Want to Donate Directly?")
st.link_button("Click Here for direct donation", "https://wustl.advancementform.com/campaign/siteman-v2/give?honor_memory=Yes&sc=SM", use_container_width=True)

st.markdown(
    """
    To donate directly:
    1. Click the link above to be directed to the Siteman Center's Donation Portal.
    2. Select a Donation Amount
    3. Choose "Other - Designation" and enter: “Marci Bikshorn Sarcoma Research Fund” into the text box!

    Thank you for your thoughtful contribution to helping find a cure. Your contribution helps fund crucial research, and every entry makes a difference.
    From the bottom of our hearts – thank you. 💜
    """
)