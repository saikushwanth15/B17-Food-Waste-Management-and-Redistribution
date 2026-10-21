"""
Smart Food Rescue - main Streamlit application
Run with:   streamlit run app.py

This file only handles: page set-up, login/registration screen, the sidebar
menu (which depends on the user's role) and routing to the right page.
The real work lives in the modules/ folder:
    modules/donor.py      -> Member 1
    modules/recipient.py  -> Member 2
    modules/analytics.py, analysis.py, reports.py -> Member 3
"""
import pandas as pd
import streamlit as st

from modules import analytics, donor, recipient
from utils import auth, storage
from utils.constants import (APP_NAME, APP_TAGLINE, ROLE_ADMIN, ROLE_DONOR,
                             ROLE_RECIPIENT)
from utils.ui import show_flash

st.set_page_config(page_title=APP_NAME, page_icon="🍲", layout="wide")

# ---------------------------------------------------------------- start-up
storage.init_storage()
auth.ensure_admin()
recipient.expire_old_donations()

if "user" not in st.session_state:
    st.session_state["user"] = None


# ----------------------------------------------------------- login / register
def login_screen():
    st.title(f"🍲 {APP_NAME}")
    st.subheader(APP_TAGLINE)
    st.write("Connecting restaurants, hostels, hotels, canteens and supermarkets that have "
             "**surplus food** with NGOs that feed people in need.")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            go = st.form_submit_button("Login", type="primary")
        if go:
            user = auth.login_user(email, password)
            if user:
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("Invalid email or password.")
        st.caption("Demo accounts (after running seed_data.py): admin@foodrescue.com / admin123, "
                   "spice@demo.com / demo123 (donor), hope@demo.com / demo123 (NGO)")

    with tab_register:
        with st.form("register_form"):
            c1, c2 = st.columns(2)
            role = c1.selectbox("I am a", [ROLE_DONOR, ROLE_RECIPIENT])
            name = c2.text_input("Full name *")
            organization = c1.text_input("Organisation (restaurant / hostel / NGO name)")
            city = c2.text_input("City *")
            email = c1.text_input("Email *")
            phone = c2.text_input("Phone (10 digits) *")
            password = c1.text_input("Password * (min 6 characters)", type="password")
            confirm = c2.text_input("Confirm password *", type="password")
            go = st.form_submit_button("Create account", type="primary")
        if go:
            ok, message = auth.register_user(name, email, password, confirm, role,
                                             phone, organization, city)
            (st.success if ok else st.error)(message)


# ------------------------------------------------------------------- menus
def menu_for(role):
    """Menu label -> function to call. Every function receives the user dict."""
    if role == ROLE_DONOR:
        return {
            "Dashboard": donor.donor_dashboard,
            "Add Donation": donor.add_donation,
            "My Donations": donor.my_donations,
            "Incoming Requests": recipient.manage_requests,
            "Analytics": lambda u: analytics.analytics_dashboard(),
            "Reports": lambda u: analytics.reports_page(),
        }
    if role == ROLE_RECIPIENT:
        return {
            "Dashboard": recipient.recipient_dashboard,
            "Available Food": recipient.available_food,
            "My Requests": recipient.my_requests,
            "Collection & Distribution": recipient.track_distribution,
            "Analytics": lambda u: analytics.analytics_dashboard(),
            "Reports": lambda u: analytics.reports_page(),
        }
    return {  # Admin
        "Analytics": lambda u: analytics.analytics_dashboard(),
        "Manage Requests": recipient.manage_requests,
        "Distribution Tracking": recipient.track_distribution,
        "All Donations": all_donations,
        "Users": users_page,
        "Reports": lambda u: analytics.reports_page(),
    }


def all_donations(user):
    st.header("All Donations")
    donor.donation_table_with_filters(storage.load("donations"), key="all")


def users_page(user):
    st.header("Registered Users")
    users = storage.load("users").drop(columns=["password"])
    st.dataframe(users, use_container_width=True, hide_index=True)
    counts = users["role"].value_counts().reset_index()
    counts.columns = ["role", "users"]
    st.bar_chart(counts, x="role", y="users")


# -------------------------------------------------------------------- main
def main():
    user = st.session_state["user"]
    if user is None:
        login_screen()
        return

    pages = menu_for(user["role"])
    with st.sidebar:
        st.title(f"🍲 {APP_NAME}")
        st.write(f"**{user['name']}**")
        st.caption(f"{user['role']}  |  {user['city']}")
        choice = st.radio("Menu", list(pages), label_visibility="collapsed")
        st.divider()
        if st.button("Logout"):
            st.session_state["user"] = None
            st.rerun()

    show_flash()
    pages[choice](user)


main()
