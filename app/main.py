import streamlit as st
from nav import home, dashboard, notes, journal

pages = {"Home": home, "Dashboard": dashboard, "Notes": notes, "Journal": journal}

def main():
    page = st.sidebar.radio("NIMOZINI", list(pages.keys()))
    pages[page].show_page()

if __name__ == "__main__":

    main()



