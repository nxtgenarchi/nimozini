import streamlit as st
from nav import home, dashboard, notes, journal

pages = {"Home": home, "Dashboard": dashboard, "Notes": notes, "Journal": journal}

def main():
    if "auth" not in st.session_state:
        st.session_state["auth"] = ""
    if st.session_state["auth"] != st.secrets["PASSWORD"]:
        st.text_input("This is a personal app. Please enter your password to continue:", type="password", key="auth")
    else:
        page = st.sidebar.radio("NIMOZINI", list(pages.keys()))
        pages[page].show_page()

if __name__ == "__main__":

    main()


