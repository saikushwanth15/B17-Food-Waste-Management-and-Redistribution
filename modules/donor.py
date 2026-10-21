"""
MEMBER 1 - Streamlit interface & Donor management
-------------------------------------------------
* Donor dashboard
* Add / edit / delete food donation records (with validation)
* Search and filter donations
All data is stored in data/donations.csv through utils.storage.
"""
from datetime import datetime, date, time, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import storage
from utils.constants import CATEGORIES, DATE_FMT, DONATION_STATUSES
from utils.ui import flash

SHOW_COLUMNS = ["donation_id", "food_name", "category", "quantity_kg", "servings",
                "city", "expiry_datetime", "status", "created_at"]


# ---------------------------------------------------------------- validation
def validate_donation(food_name, quantity, servings, city, address, expiry):
    """Return a list of error messages (empty list = form is valid)."""
    errors = []
    if len(food_name.strip()) < 3:
        errors.append("Food name must have at least 3 characters.")
    if quantity <= 0:
        errors.append("Quantity must be greater than 0 kg.")
    if servings <= 0:
        errors.append("Number of servings must be at least 1.")
    if not city.strip():
        errors.append("City is required.")
    if len(address.strip()) < 5:
        errors.append("Please enter a proper pickup address.")
    if expiry <= datetime.now():
        errors.append("Expiry date/time must be in the future.")
    return errors


# ----------------------------------------------------------------- dashboard
def donor_dashboard(user):
    st.header(f"Welcome, {user['name']}")
    donations = storage.load("donations")
    mine = donations[donations["donor_id"] == user["user_id"]].copy()

    if mine.empty:
        st.info("You have not added any donations yet. Use **Add Donation** in the menu.")
        return

    mine["quantity_kg"] = pd.to_numeric(mine["quantity_kg"], errors="coerce").fillna(0)
    mine["servings"] = pd.to_numeric(mine["servings"], errors="coerce").fillna(0)
    delivered = mine[mine["status"] == "Distributed"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total donations", len(mine))
    c2.metric("Food donated (kg)", f"{mine['quantity_kg'].sum():.1f}")
    c3.metric("Meals delivered", int(delivered["servings"].sum()))
    c4.metric("Active (Available/Reserved)",
              int(mine["status"].isin(["Available", "Reserved"]).sum()))

    left, right = st.columns(2)
    status_counts = mine["status"].value_counts().reset_index()
    status_counts.columns = ["status", "count"]
    left.plotly_chart(px.pie(status_counts, names="status", values="count",
                             title="My donations by status", hole=0.4),
                      use_container_width=True)
    cat_kg = mine.groupby("category", as_index=False)["quantity_kg"].sum()
    right.plotly_chart(px.bar(cat_kg, x="category", y="quantity_kg",
                              title="Food donated by category (kg)"),
                       use_container_width=True)

    st.subheader("Recent donations")
    recent = mine.sort_values("created_at", ascending=False).head(5)
    st.dataframe(recent[SHOW_COLUMNS], use_container_width=True, hide_index=True)


# ------------------------------------------------------------ add a donation
def add_donation(user):
    st.header("Add a Food Donation")
    st.caption("Fill in the details of the surplus food. NGOs will see it and send requests.")

    with st.form("add_donation_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        food_name = col1.text_input("Food item name *", placeholder="e.g. Vegetable biryani")
        category = col2.selectbox("Category *", CATEGORIES)
        quantity = col1.number_input("Quantity (kg) *", min_value=0.0, step=0.5, value=1.0)
        servings = col2.number_input("Approx. servings (meals) *", min_value=0, step=1, value=10)
        city = col1.text_input("City *", value=user.get("city", ""))
        address = col2.text_input("Pickup address *")
        exp_date = col1.date_input("Best before (date) *", value=date.today())
        exp_time = col2.time_input("Best before (time) *",
                                   value=(datetime.now() + timedelta(hours=6)).time().replace(second=0, microsecond=0))
        notes = st.text_area("Notes (optional)", placeholder="Veg/non-veg, packaging, contact person ...")
        submitted = st.form_submit_button("Submit donation", type="primary")

    if submitted:
        expiry = datetime.combine(exp_date, exp_time)
        errors = validate_donation(food_name, quantity, servings, city, address, expiry)
        if errors:
            for e in errors:
                st.error(e)
            return
        new_id = storage.add_record("donations", {
            "donor_id": user["user_id"], "donor_name": user["name"],
            "food_name": food_name.strip(), "category": category,
            "quantity_kg": round(quantity, 2), "servings": int(servings),
            "city": city.strip().title(), "pickup_address": address.strip(),
            "expiry_datetime": expiry.strftime(DATE_FMT), "notes": notes.strip(),
            "status": "Available", "created_at": storage.now_str(),
        })
        st.success(f"Thank you! Donation **{new_id}** has been added and is now visible to NGOs.")


# --------------------------------------------- reusable search / filter table
def donation_table_with_filters(df, key):
    """Show a donation table with search + filters. Returns the filtered DataFrame."""
    c1, c2, c3, c4 = st.columns(4)
    search = c1.text_input("Search food / donor", key=f"{key}_search")
    status = c2.multiselect("Status", DONATION_STATUSES, key=f"{key}_status")
    category = c3.multiselect("Category", CATEGORIES, key=f"{key}_cat")
    cities = sorted(c for c in df["city"].unique() if c)
    city = c4.multiselect("City", cities, key=f"{key}_city")

    result = df.copy()
    if search:
        text = (result["food_name"] + " " + result["donor_name"]).str.lower()
        result = result[text.str.contains(search.strip().lower(), regex=False)]
    if status:
        result = result[result["status"].isin(status)]
    if category:
        result = result[result["category"].isin(category)]
    if city:
        result = result[result["city"].isin(city)]

    st.caption(f"Showing {len(result)} of {len(df)} donations")
    st.dataframe(result[SHOW_COLUMNS + ["donor_name"]].sort_values("created_at", ascending=False),
                 use_container_width=True, hide_index=True)
    return result


# ------------------------------------------------- my donations (edit/delete)
def my_donations(user):
    st.header("My Donations")
    donations = storage.load("donations")
    mine = donations[donations["donor_id"] == user["user_id"]]
    if mine.empty:
        st.info("No donations yet.")
        return

    donation_table_with_filters(mine, key="mine")

    st.divider()
    st.subheader("Edit or delete a donation")
    st.caption("Only donations with status **Available** can be changed.")
    editable = mine[mine["status"] == "Available"]
    if editable.empty:
        st.info("You have no editable donations right now.")
        return

    labels = {row.donation_id: f"{row.donation_id} - {row.food_name} ({row.quantity_kg} kg)"
              for row in editable.itertuples()}
    chosen = st.selectbox("Select a donation", list(labels), format_func=labels.get)
    record = storage.get_record("donations", chosen)

    tab_edit, tab_delete = st.tabs(["Edit", "Delete"])

    with tab_edit:
        with st.form(f"edit_form_{chosen}"):
            col1, col2 = st.columns(2)
            food_name = col1.text_input("Food item name", value=record["food_name"])
            category = col2.selectbox("Category", CATEGORIES,
                                      index=CATEGORIES.index(record["category"])
                                      if record["category"] in CATEGORIES else 0)
            quantity = col1.number_input("Quantity (kg)", min_value=0.0, step=0.5,
                                         value=float(record["quantity_kg"] or 0))
            servings = col2.number_input("Servings", min_value=0, step=1,
                                         value=int(float(record["servings"] or 0)))
            city = col1.text_input("City", value=record["city"])
            address = col2.text_input("Pickup address", value=record["pickup_address"])
            old_expiry = datetime.strptime(record["expiry_datetime"], DATE_FMT)
            exp_date = col1.date_input("Best before (date)", value=old_expiry.date())
            exp_time = col2.time_input("Best before (time)", value=old_expiry.time())
            notes = st.text_area("Notes", value=record["notes"])
            save_clicked = st.form_submit_button("Save changes", type="primary")

        if save_clicked:
            expiry = datetime.combine(exp_date, exp_time)
            errors = validate_donation(food_name, quantity, servings, city, address, expiry)
            if errors:
                for e in errors:
                    st.error(e)
            else:
                storage.update_record("donations", chosen, {
                    "food_name": food_name.strip(), "category": category,
                    "quantity_kg": round(quantity, 2), "servings": int(servings),
                    "city": city.strip().title(), "pickup_address": address.strip(),
                    "expiry_datetime": expiry.strftime(DATE_FMT), "notes": notes.strip(),
                })
                flash(f"Donation {chosen} updated.")
                st.rerun()

    with tab_delete:
        st.warning(f"This will permanently delete donation **{chosen}**.")
        confirm = st.checkbox("Yes, I want to delete this donation", key=f"confirm_{chosen}")
        if st.button("Delete donation", disabled=not confirm):
            storage.delete_record("donations", chosen)
            # also remove any pending requests that pointed to it
            requests = storage.load("requests")
            for rid in requests[(requests["donation_id"] == chosen)]["request_id"]:
                storage.delete_record("requests", rid)
            flash(f"Donation {chosen} deleted.")
            st.rerun()
