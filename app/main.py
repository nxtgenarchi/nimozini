import streamlit as st
from nav import home, dashboard, notes, journal

pages = {"Home": home, "Dashboard": dashboard, "Notes": notes, "Journal": journal}

def main():
    if "auth" not in st.session_state:
        st.session_state["is_auth"] = False
    placeholder = st.empty()
    if not st.session_state["is_auth"]:
        auth_value = placeholder.text_input("This is a private app. Please enter the correct password to continue:", type="password", key="auth_input")
        if auth_value:
            if auth_value == st.secrets.get("PASSWORD", ""):
                st.session_state["is_auth"] = True
            else:
                st.error("Incorrect password.")
                return
        else:
            return
    placeholder.write("")
    page = st.sidebar.radio("NIMOZINI", list(pages.keys()))
    pages[page].show_page()

if __name__ == "__main__":

    main()










