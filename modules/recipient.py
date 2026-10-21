"""
MEMBER 2 - Recipient / NGO & Food Distribution management
----------------------------------------------------------
* Recipient/NGO dashboard
* Browse available surplus food and send requests
* Approve / reject requests
* Track collection and distribution
* Keep donation + request statuses in sync
Data: data/requests.csv and data/distributions.csv (plus donations.csv status).
"""
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from utils import storage
from utils.constants import CATEGORIES, DATE_FMT, ROLE_ADMIN, ROLE_DONOR
from utils.ui import flash


# ------------------------------------------------------- background clean-up
def expire_old_donations():
    """Mark Available donations whose best-before time has passed as Expired,
    and reject any pending requests that were waiting for them."""
    donations = storage.load("donations")
    now = datetime.now()
    for row in donations[donations["status"] == "Available"].itertuples():
        try:
            expired = datetime.strptime(row.expiry_datetime, DATE_FMT) < now
        except ValueError:
            continue
        if expired:
            storage.update_record("donations", row.donation_id, {"status": "Expired"})
            requests = storage.load("requests")
            pending = requests[(requests["donation_id"] == row.donation_id)
                               & (requests["status"] == "Pending")]
            for rid in pending["request_id"]:
                storage.update_record("requests", rid, {"status": "Rejected",
                                                        "decided_at": storage.now_str()})


# ----------------------------------------------------------------- dashboard
def recipient_dashboard(user):
    st.header(f"Welcome, {user['name']}")
    if user.get("organization"):
        st.caption(user["organization"])

    donations = storage.load("donations")
    requests = storage.load("requests")
    dists = storage.load("distributions")
    my_req = requests[requests["recipient_id"] == user["user_id"]]
    my_dist = dists[dists["recipient_id"] == user["user_id"]].copy()
    my_dist["people_served"] = pd.to_numeric(my_dist["people_served"], errors="coerce").fillna(0)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Food available now", int((donations["status"] == "Available").sum()))
    c2.metric("My pending requests", int((my_req["status"] == "Pending").sum()))
    c3.metric("Approved (to collect)", int((my_req["status"] == "Approved").sum()))
    c4.metric("Collected (to distribute)", int((my_req["status"] == "Collected").sum()))
    c5.metric("People served", int(my_dist["people_served"].sum()))

    if my_req.empty:
        st.info("You have not requested any food yet. Open **Available Food** to get started.")
        return

    counts = my_req["status"].value_counts().reset_index()
    counts.columns = ["status", "count"]
    st.plotly_chart(px.bar(counts, x="status", y="count", title="My requests by status"),
                    use_container_width=True)


# ------------------------------------------------------- available food list
def available_food(user):
    st.header("Available Surplus Food")
    donations = storage.load("donations")
    available = donations[donations["status"] == "Available"].copy()
    requests = storage.load("requests")

    c1, c2, c3 = st.columns(3)
    search = c1.text_input("Search food item")
    category = c2.multiselect("Category", CATEGORIES)
    city = c3.multiselect("City", sorted(c for c in available["city"].unique() if c))
    if search:
        available = available[available["food_name"].str.lower().str.contains(search.strip().lower(), regex=False)]
    if category:
        available = available[available["category"].isin(category)]
    if city:
        available = available[available["city"].isin(city)]

    if available.empty:
        st.info("No surplus food matches your filters right now.")
        return

    for row in available.sort_values("expiry_datetime").itertuples():
        already = requests[(requests["donation_id"] == row.donation_id)
                           & (requests["recipient_id"] == user["user_id"])
                           & (requests["status"].isin(["Pending", "Approved"]))]
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.subheader(f"{row.food_name}  -  {row.quantity_kg} kg")
            left.write(f"**Category:** {row.category}  |  **Servings:** {row.servings}  |  **City:** {row.city}")
            left.write(f"**Donor:** {row.donor_name}  |  **Best before:** {row.expiry_datetime}")
            if row.notes:
                left.caption(row.notes)
            if not already.empty:
                right.success("You already requested this item.")
                continue
            message = right.text_input("Message to donor (optional)", key=f"msg_{row.donation_id}")
            if right.button("Request this food", key=f"req_{row.donation_id}", type="primary"):
                storage.add_record("requests", {
                    "donation_id": row.donation_id, "recipient_id": user["user_id"],
                    "recipient_name": user.get("organization") or user["name"],
                    "message": message.strip(), "status": "Pending",
                    "requested_at": storage.now_str(), "decided_at": "",
                })
                flash(f"Request sent for {row.food_name}. You will be notified once it is approved.")
                st.rerun()


# --------------------------------------------------------------- my requests
def my_requests(user):
    st.header("My Requests")
    requests = storage.load("requests")
    mine = requests[requests["recipient_id"] == user["user_id"]]
    if mine.empty:
        st.info("You have not made any requests yet.")
        return

    donations = storage.load("donations")[["donation_id", "food_name", "quantity_kg", "city",
                                           "pickup_address", "expiry_datetime"]]
    merged = mine.merge(donations, on="donation_id", how="left")
    # pickup address is shown only after approval
    merged.loc[~merged["status"].isin(["Approved", "Collected", "Distributed"]), "pickup_address"] = "(visible after approval)"
    st.dataframe(merged[["request_id", "donation_id", "food_name", "quantity_kg", "city",
                         "pickup_address", "status", "requested_at", "decided_at"]],
                 use_container_width=True, hide_index=True)

    pending = mine[mine["status"] == "Pending"]
    if not pending.empty:
        st.subheader("Cancel a pending request")
        rid = st.selectbox("Request", pending["request_id"].tolist())
        if st.button("Cancel request"):
            storage.update_record("requests", rid, {"status": "Cancelled",
                                                    "decided_at": storage.now_str()})
            flash(f"Request {rid} cancelled.")
            st.rerun()


# ------------------------------------------- approve / reject (donor + admin)
def manage_requests(user):
    """Donors see requests for their own food; the Admin sees every request."""
    st.header("Incoming Requests" if user["role"] == ROLE_DONOR else "Manage Requests")
    requests = storage.load("requests")
    donations = storage.load("donations")
    merged = requests.merge(donations[["donation_id", "donor_id", "food_name", "quantity_kg",
                                       "city", "status"]].rename(columns={"status": "donation_status"}),
                            on="donation_id", how="left")
    if user["role"] == ROLE_DONOR:
        merged = merged[merged["donor_id"] == user["user_id"]]

    pending = merged[merged["status"] == "Pending"]
    st.subheader(f"Pending requests ({len(pending)})")
    if pending.empty:
        st.info("No pending requests.")

    for row in pending.itertuples():
        with st.container(border=True):
            left, right = st.columns([3, 2])
            left.write(f"**{row.recipient_name}** wants **{row.food_name}** ({row.quantity_kg} kg, {row.city})")
            left.caption(f"Request {row.request_id}  |  sent {row.requested_at}")
            if row.message:
                left.write(f"Message: _{row.message}_")
            if row.donation_status != "Available":
                right.warning("This donation is no longer available.")
                continue
            if right.button("Approve", key=f"ok_{row.request_id}", type="primary"):
                approve_request(row.request_id, row.donation_id)
                flash(f"Request {row.request_id} approved. Donation reserved.")
                st.rerun()
            if right.button("Reject", key=f"no_{row.request_id}"):
                storage.update_record("requests", row.request_id,
                                      {"status": "Rejected", "decided_at": storage.now_str()})
                flash(f"Request {row.request_id} rejected.", "warning")
                st.rerun()

    st.subheader("Request history")
    history = merged[merged["status"] != "Pending"]
    if history.empty:
        st.caption("Nothing here yet.")
    else:
        st.dataframe(history[["request_id", "donation_id", "food_name", "recipient_name",
                              "status", "requested_at", "decided_at"]],
                     use_container_width=True, hide_index=True)


def approve_request(request_id, donation_id):
    """Approve one request, reserve the donation and reject all competing requests."""
    now = storage.now_str()
    storage.update_record("requests", request_id, {"status": "Approved", "decided_at": now})
    storage.update_record("donations", donation_id, {"status": "Reserved"})
    others = storage.load("requests")
    others = others[(others["donation_id"] == donation_id) & (others["status"] == "Pending")
                    & (others["request_id"] != request_id)]
    for rid in others["request_id"]:
        storage.update_record("requests", rid, {"status": "Rejected", "decided_at": now})


# ----------------------------------------- track collection and distribution
def track_distribution(user):
    """Recipients track their own requests; the Admin can see and update all."""
    st.header("Collection & Distribution Tracking")
    requests = storage.load("requests")
    if user["role"] != ROLE_ADMIN:
        requests = requests[requests["recipient_id"] == user["user_id"]]

    donations = storage.load("donations")[["donation_id", "food_name", "quantity_kg",
                                           "pickup_address", "city", "donor_name"]]
    merged = requests.merge(donations, on="donation_id", how="left")

    st.subheader("1. Approved - waiting to be collected")
    approved = merged[merged["status"] == "Approved"]
    if approved.empty:
        st.caption("Nothing waiting for collection.")
    for row in approved.itertuples():
        with st.container(border=True):
            st.write(f"**{row.food_name}** ({row.quantity_kg} kg) from **{row.donor_name}**")
            st.write(f"Pick-up: {row.pickup_address}, {row.city}")
            st.caption(f"Request {row.request_id} by {row.recipient_name}")
            if st.button("Mark as collected", key=f"col_{row.request_id}", type="primary"):
                storage.add_record("distributions", {
                    "request_id": row.request_id, "donation_id": row.donation_id,
                    "recipient_id": row.recipient_id, "recipient_name": row.recipient_name,
                    "collected_at": storage.now_str(), "distributed_at": "",
                    "people_served": 0, "distribution_location": "", "notes": "",
                    "status": "Collected",
                })
                storage.update_record("requests", row.request_id, {"status": "Collected"})
                storage.update_record("donations", row.donation_id, {"status": "Collected"})
                flash("Marked as collected. Record the distribution once the food is handed out.")
                st.rerun()

    st.subheader("2. Collected - record distribution")
    collected = merged[merged["status"] == "Collected"]
    if collected.empty:
        st.caption("Nothing waiting for distribution.")
    for row in collected.itertuples():
        with st.container(border=True):
            st.write(f"**{row.food_name}** ({row.quantity_kg} kg) - request {row.request_id}")
            with st.form(f"dist_form_{row.request_id}"):
                people = st.number_input("People served", min_value=1, step=1, value=10)
                location = st.text_input("Distribution location *", placeholder="e.g. Shelter home, Kukatpally")
                notes = st.text_input("Notes (optional)")
                done = st.form_submit_button("Mark as distributed", type="primary")
            if done:
                if len(location.strip()) < 3:
                    st.error("Please enter where the food was distributed.")
                else:
                    dists = storage.load("distributions")
                    dist_id = dists[dists["request_id"] == row.request_id]["distribution_id"].iloc[0]
                    storage.update_record("distributions", dist_id, {
                        "distributed_at": storage.now_str(), "people_served": int(people),
                        "distribution_location": location.strip(), "notes": notes.strip(),
                        "status": "Distributed",
                    })
                    storage.update_record("requests", row.request_id, {"status": "Distributed"})
                    storage.update_record("donations", row.donation_id, {"status": "Distributed"})
                    flash("Distribution recorded. Thank you for reducing food waste!")
                    st.rerun()

    st.subheader("Distribution history")
    dists = storage.load("distributions")
    if user["role"] != ROLE_ADMIN:
        dists = dists[dists["recipient_id"] == user["user_id"]]
    if dists.empty:
        st.caption("No distributions recorded yet.")
    else:
        st.dataframe(dists, use_container_width=True, hide_index=True)
