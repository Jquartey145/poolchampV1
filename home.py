import streamlit as st
from firebase_admin import firestore
import auth_functions

def app():
    st.subheader('Rules and Details Here')

    st.text_area(label='#',value='Please wait this page is under construction..')