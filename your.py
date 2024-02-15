import streamlit as st
from firebase_admin import firestore

  
def app():
    st.subheader('Team Info goes here')

    st.text_area(label='#',value='Please wait this page is under construction..')  