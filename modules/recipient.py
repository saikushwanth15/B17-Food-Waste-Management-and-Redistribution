"""
================================================================================
MODULE: recipient.py
MEMBER 2 DELIVERABLE: N Charya Vishwa
================================================================================
Recipient / NGO Workflow & Distribution Tracking Module.

Responsibilities:
1. Recipient & NGO Dashboard: Impact KPIs, active requests, and people fed.
2. Available Surplus Food Catalog: Real-time search, filters, urgency countdowns,
   and pickup coordination request forms.
3. Donation Request Lifecycle:
   - NGOs submit collection requests with vehicle type and pickup ETA.
   - Donors and Admins approve or reject requests.
   - Approval reserves food and automatically rejects conflicting competing requests.
4. Two-Step Distribution Tracking:
   - Step 1: Approved -> Mark Collected (sets status to 'Collected').
   - Step 2: Collected -> Record Distribution (headcount of people served,
     delivery location, and marks status as 'Distributed').
5. Automated Expiry Maintenance: Automatically flags expired surplus food and rejects
   pending requests.
6. Pure CSV persistence via utils.storage (strictly NO SQL).
================================================================================
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import storage
from utils.constants import CATEGORIES, DATE_FMT, ROLE_ADMIN, ROLE_DONOR
from utils.ui import flash


# ==============================================================================
# 1. DECOUPLED BUSINESS LOGIC & VALIDATION (Decoupled for Unit Testing)
# ==============================================================================

def validate_distribution_entry(people_served: int, location: str) -> List[str]:
    """
    Validate distribution input fields before committing to distributions.csv.
    Returns: List of error messages (empty list [] = valid).
    """
    errors: List[str] = []
    try:
        count = int(people_served)
        if count <= 0:
            errors.append("People served must be at least 1 person.")
        elif count > 50000:
            errors.append("People served exceeds reasonable single-distribution ceiling (50,000).")
    except (ValueError, TypeError):
        errors.append("People served must be a valid whole number.")

    loc_clean = str(location).strip()
    if len(loc_clean) < 3:
        errors.append("Distribution location must contain at least 3 characters (e.g. Slum Shelter, Ward 4).")
    elif len(loc_clean) > 150:
        errors.append("Distribution location text cannot exceed 150 characters.")

    return errors


def filter_available_food(
    df: pd.DataFrame,
    search_query: str = "",
    categories: Optional[List[str]] = None,
    cities: Optional[List[str]] = None,
    sort_by: str = "Expiring Soonest"
) -> pd.DataFrame:
    """
    Filter available surplus food listings by keyword, category, city, and sort order.
    Pure Pandas function without Streamlit dependencies for automated testing.
    """
    if df.empty:
        return df.copy()

    # Ensure status is Available
    res = df[df["status"] == "Available"].copy()
    if res.empty:
        return res

    # 1. Text Search across food name, donor name, and notes
    if search_query and search_query.strip():
        q = search_query.strip().lower()
        food_col = res["food_name"].fillna("").astype(str) if "food_name" in res.columns else pd.Series("", index=res.index)
        donor_col = res["donor_name"].fillna("").astype(str) if "donor_name" in res.columns else pd.Series("", index=res.index)
        notes_col = res["notes"].fillna("").astype(str) if "notes" in res.columns else pd.Series("", index=res.index)
        search_corpus = (food_col + " " + donor_col + " " + notes_col).str.lower()
        res = res[search_corpus.str.contains(q, regex=False)]

    # 2. Categorical Filters
    if categories:
        res = res[res["category"].isin(categories)]
    if cities:
        res = res[res["city"].isin(cities)]

    # 3. Sorting Options
    if sort_by == "Expiring Soonest" and "expiry_datetime" in res.columns:
        res["_tmp_exp"] = pd.to_datetime(res["expiry_datetime"], errors="coerce")
        res = res.sort_values("_tmp_exp", ascending=True).drop(columns=["_tmp_exp"])
    elif sort_by == "Quantity (Highest First)" and "quantity_kg" in res.columns:
        res["_tmp_qty"] = pd.to_numeric(res["quantity_kg"], errors="coerce").fillna(0)
        res = res.sort_values("_tmp_qty", ascending=False).drop(columns=["_tmp_qty"])
    elif sort_by == "Newest First" and "created_at" in res.columns:
        res = res.sort_values("created_at", ascending=False)
    elif sort_by == "Oldest First" and "created_at" in res.columns:
        res = res.sort_values("created_at", ascending=True)

    return res.reset_index(drop=True)


def calculate_ngo_metrics(
    user_id: str,
    donations_df: pd.DataFrame,
    requests_df: pd.DataFrame,
    dists_df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Calculate summary impact numbers for a specific recipient NGO organization.
    """
    available_count = int((donations_df["status"] == "Available").sum()) if not donations_df.empty else 0
    available_kg = float(donations_df.loc[donations_df["status"] == "Available", "quantity_kg"].astype(float).sum()) if not donations_df.empty else 0.0

    my_reqs = requests_df[requests_df["recipient_id"] == user_id] if not requests_df.empty else pd.DataFrame()
    pending_count = int((my_reqs["status"] == "Pending").sum()) if not my_reqs.empty else 0
    approved_count = int((my_reqs["status"] == "Approved").sum()) if not my_reqs.empty else 0
    collected_count = int((my_reqs["status"] == "Collected").sum()) if not my_reqs.empty else 0
    
    my_dists = dists_df[dists_df["recipient_id"] == user_id] if not dists_df.empty else pd.DataFrame()
    total_distributed = int((my_dists["status"] == "Distributed").sum()) if not my_dists.empty else 0
    
    people_served = 0
    if not my_dists.empty and "people_served" in my_dists.columns:
        people_served = int(pd.to_numeric(my_dists["people_served"], errors="coerce").fillna(0).sum())

    return {
        "available_listings": available_count,
        "available_food_kg": round(available_kg, 1),
        "my_pending_requests": pending_count,
        "my_approved_awaiting_pickup": approved_count,
        "my_collected_awaiting_dist": collected_count,
        "my_completed_distributions": total_distributed,
        "total_people_served": people_served,
    }


# ==============================================================================
# 2. AUTOMATIC EXPIRY HANDLING
# ==============================================================================

def expire_old_donations() -> int:
    """
    Background maintenance: Transition Available donations whose best-before timestamp
    has elapsed to 'Expired', and automatically reject pending requests attached to them.
    Returns: Number of records transitioned to Expired.
    """
    donations = storage.load("donations")
    if donations.empty or "expiry_datetime" not in donations.columns:
        return 0

    now = datetime.now()
    expired_count = 0

    for row in donations[donations["status"] == "Available"].itertuples():
        try:
            exp_time = datetime.strptime(row.expiry_datetime, DATE_FMT)
            if exp_time < now:
                storage.update_record("donations", row.donation_id, {"status": "Expired"})
                expired_count += 1
                
                # Reject pending requests on this expired donation
                requests = storage.load("requests")
                pending = requests[(requests["donation_id"] == row.donation_id) & (requests["status"] == "Pending")]
                for rid in pending["request_id"]:
                    storage.update_record("requests", rid, {
                        "status": "Rejected",
                        "decided_at": storage.now_str()
                    })
        except Exception:
            continue

    return expired_count


# ==============================================================================
# 3. RECIPIENT / NGO DASHBOARD
# ==============================================================================

def recipient_dashboard(user: Dict[str, Any]) -> None:
    """Render personalized recipient/NGO operational dashboard."""
    st.header(f"🤝 Welcome, {user.get('name', 'NGO Partner')}")
    st.caption(f"**Organisation:** {user.get('organization', 'Relief Partner')} &nbsp;|&nbsp; **City:** {user.get('city', 'Regional Hub')}")

    donations = storage.load("donations")
    requests = storage.load("requests")
    dists = storage.load("distributions")

    metrics = calculate_ngo_metrics(user["user_id"], donations, requests, dists)

    # Metric Cards Row 1: Immediate Action Items
    st.markdown("### 📋 Operational Status")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🍲 Surplus Available Now", f"{metrics['available_listings']} listings", f"{metrics['available_food_kg']} kg total")
    c2.metric("⏳ Pending Requests", f"{metrics['my_pending_requests']}", help="Requests awaiting donor review")
    c3.metric("🚚 Approved (Awaiting Pickup)", f"{metrics['my_approved_awaiting_pickup']}", help="Ready for physical collection")
    c4.metric("📦 Collected (To Distribute)", f"{metrics['my_collected_awaiting_dist']}", help="Food in transit / distribution")

    # Metric Cards Row 2: Impact Metrics
    c5, c6 = st.columns(2)
    c5.metric("✨ Total Distributions Completed", f"{metrics['my_completed_distributions']}")
    c6.metric("👥 Total Beneficiaries Served", f"{metrics['total_people_served']:,} people fed", "SDG 2 Impact")

    st.divider()

    my_req = requests[requests["recipient_id"] == user["user_id"]]
    if my_req.empty:
        st.info("ℹ️ You haven't made any food requests yet. Click **Available Food** in the menu to browse surplus listings!")
        return

    # Visualizations
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.markdown("#### My Requests by Status")
        status_counts = my_req["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        fig_req = px.bar(
            status_counts,
            x="status",
            y="count",
            color="status",
            text_auto=True,
            color_discrete_map={
                "Pending": "#F59E0B",
                "Approved": "#3B82F6",
                "Collected": "#8B5CF6",
                "Distributed": "#10B981",
                "Rejected": "#EF4444",
                "Cancelled": "#9CA3AF"
            }
        )
        fig_req.update_layout(xaxis_title="", yaxis_title="Number of Requests", showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig_req, use_container_width=True)

    with col_chart2:
        st.markdown("#### Beneficiaries Served by Location")
        my_dists = dists[dists["recipient_id"] == user["user_id"]].copy()
        if not my_dists.empty and "people_served" in my_dists.columns:
            my_dists["people_served"] = pd.to_numeric(my_dists["people_served"], errors="coerce").fillna(0)
            completed_dists = my_dists[my_dists["status"] == "Distributed"]
            if not completed_dists.empty:
                loc_summary = completed_dists.groupby("distribution_location", as_index=False)["people_served"].sum()
                fig_loc = px.pie(
                    loc_summary,
                    names="distribution_location",
                    values="people_served",
                    hole=0.4,
                    title="Beneficiary Share by Distribution Site"
                )
                fig_loc.update_layout(margin=dict(t=10, b=10))
                st.plotly_chart(fig_loc, use_container_width=True)
            else:
                st.info("No completed distributions yet to display location breakdown.")
        else:
            st.info("No completed distributions recorded yet.")


# ==============================================================================
# 4. AVAILABLE SURPLUS FOOD CATALOG & REQUEST SUBMISSION
# ==============================================================================

def available_food(user: Dict[str, Any]) -> None:
    """Render real-time surplus food catalog with freshness countdown and request form."""
    st.header("🍱 Available Surplus Food Catalog")
    st.caption("Browse edible surplus food donated by restaurants, canteens, and hostels. Submit a request to coordinate collection.")

    donations = storage.load("donations")
    requests = storage.load("requests")

    # Filter Bar
    c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
    search_q = c1.text_input("🔍 Search Food Item / Notes", placeholder="e.g. Biryani, Rice, Bread...")
    selected_cats = c2.multiselect("Category", CATEGORIES)
    
    unique_cities = sorted([c for c in donations["city"].dropna().unique() if c]) if "city" in donations.columns else []
    selected_cities = c3.multiselect("City", unique_cities)
    
    sort_by = c4.selectbox("Sort Order", ["Expiring Soonest", "Quantity (Highest First)", "Newest First"])

    available_df = filter_available_food(
        donations,
        search_query=search_q,
        categories=selected_cats,
        cities=selected_cities,
        sort_by=sort_by
    )

    if available_df.empty:
        st.info("ℹ️ No surplus food matches your filter criteria right now. Check back soon!")
        return

    st.markdown(f"**Found {len(available_df)} available surplus listings:**")
    now_dt = datetime.now()

    for row in available_df.itertuples():
        # Freshness calculation
        try:
            exp_dt = datetime.strptime(row.expiry_datetime, DATE_FMT)
            hours_diff = (exp_dt - now_dt).total_seconds() / 3600.0
            if hours_diff <= 0:
                continue
            elif hours_diff < 4:
                urgency_badge = f"🔥 **Expiring in {int(hours_diff)}h {int((hours_diff%1)*60)}m**"
            else:
                urgency_badge = f"⏰ Fresh for ~{int(hours_diff)} hours"
        except Exception:
            urgency_badge = "⏰ Scheduled Expiry"

        # Check if already requested by this NGO
        already_requested = not requests.empty and (
            (requests["donation_id"] == row.donation_id) &
            (requests["recipient_id"] == user["user_id"]) &
            (requests["status"].isin(["Pending", "Approved", "Collected"]))
        ).any()

        with st.container(border=True):
            col_info, col_action = st.columns([3, 2])
            with col_info:
                st.subheader(f"{row.food_name} — {row.quantity_kg} kg")
                st.markdown(f"**Category:** `{row.category}` &nbsp;|&nbsp; **Est. Servings:** `{row.servings} portions` &nbsp;|&nbsp; **City:** `{row.city}`")
                st.markdown(f"**Donor:** {row.donor_name} &nbsp;|&nbsp; **Best Before:** `{row.expiry_datetime}` ({urgency_badge})")
                if getattr(row, "notes", None):
                    st.caption(f"📝 {row.notes}")

            with col_action:
                if already_requested:
                    st.info("✅ **Request Sent:** You have already submitted a request for this listing.")
                else:
                    st.markdown("**Request this Food:**")
                    vehicle_choice = st.selectbox(
                        "Vehicle / Transport Type",
                        ["Two-Wheeler with Bags", "Auto Rickshaw / Cargo Bike", "Dedicated Van / Tempo", "On-Foot / Volunteer Carry"],
                        key=f"veh_{row.donation_id}"
                    )
                    eta_mins = st.selectbox(
                        "Estimated Pickup Window",
                        ["Within 1 hour", "Within 2 hours", "Within 4 hours", "Same-day evening"],
                        key=f"eta_{row.donation_id}"
                    )
                    req_message = st.text_input(
                        "Message to Donor (Optional)",
                        placeholder="e.g. Feeding 30 children at Sunrise Orphanage.",
                        key=f"msg_{row.donation_id}"
                    )

                    if st.button("🚀 Send Food Request", key=f"btn_{row.donation_id}", type="primary"):
                        full_message = f"[{vehicle_choice} | ETA: {eta_mins}]"
                        if req_message.strip():
                            full_message += f" {req_message.strip()}"

                        new_req_id = storage.add_record("requests", {
                            "donation_id": row.donation_id,
                            "recipient_id": user["user_id"],
                            "recipient_name": user.get("organization") or user.get("name", "NGO"),
                            "message": full_message,
                            "status": "Pending",
                            "requested_at": storage.now_str(),
                            "decided_at": "",
                        })
                        flash(f"✅ Request {new_req_id} sent to donor {row.donor_name}!")
                        st.rerun()


# ==============================================================================
# 5. MY REQUESTS CATALOG (NGO View)
# ==============================================================================

def my_requests(user: Dict[str, Any]) -> None:
    """View and manage requests submitted by this NGO."""
    st.header("📋 My Surplus Food Requests")
    requests = storage.load("requests")
    mine = requests[requests["recipient_id"] == user["user_id"]].copy()

    if mine.empty:
        st.info("You haven't submitted any food requests yet.")
        return

    donations = storage.load("donations")[["donation_id", "food_name", "quantity_kg", "city", "pickup_address", "expiry_datetime", "donor_name"]]
    merged = mine.merge(donations, on="donation_id", how="left")

    # Data Protection: Reveal physical pickup address ONLY after donor approval
    merged.loc[~merged["status"].isin(["Approved", "Collected", "Distributed"]), "pickup_address"] = "🔒 (Revealed upon donor approval)"

    display_cols = ["request_id", "donation_id", "food_name", "quantity_kg", "city", "pickup_address", "status", "requested_at", "decided_at"]
    cols_to_render = [c for c in display_cols if c in merged.columns]
    
    st.dataframe(
        merged[cols_to_render].sort_values("requested_at", ascending=False),
        use_container_width=True,
        hide_index=True
    )

    # Allow cancelling pending requests
    pending = mine[mine["status"] == "Pending"]
    if not pending.empty:
        st.divider()
        st.subheader("❌ Cancel a Pending Request")
        c_sel, c_btn = st.columns([3, 1])
        cancel_id = c_sel.selectbox("Select Pending Request to Withdraw", pending["request_id"].tolist())
        if c_btn.button("Cancel Request"):
            storage.update_record("requests", cancel_id, {
                "status": "Cancelled",
                "decided_at": storage.now_str()
            })
            flash(f"Request {cancel_id} has been cancelled.")
            st.rerun()


# ==============================================================================
# 6. REQUEST APPROVAL & CONFLICT RESOLUTION (Donor & Admin)
# ==============================================================================

def approve_request(request_id: str, donation_id: str) -> None:
    """
    Approve one NGO request, reserve the donation, and automatically
    reject all competing pending requests for the same food item.
    """
    now_ts = storage.now_str()
    # 1. Update approved request
    storage.update_record("requests", request_id, {"status": "Approved", "decided_at": now_ts})
    # 2. Reserve donation
    storage.update_record("donations", donation_id, {"status": "Reserved"})
    # 3. Automatically reject competing requests
    all_requests = storage.load("requests")
    competing = all_requests[
        (all_requests["donation_id"] == donation_id) &
        (all_requests["status"] == "Pending") &
        (all_requests["request_id"] != request_id)
    ]
    for rid in competing["request_id"]:
        storage.update_record("requests", rid, {
            "status": "Rejected",
            "decided_at": now_ts
        })


def manage_requests(user: Dict[str, Any]) -> None:
    """Manage incoming requests (Donors manage their own listings; Admins manage all)."""
    is_admin = user.get("role") == ROLE_ADMIN
    st.header("📥 Manage Incoming Food Requests" if not is_admin else "🛡️ System Request Governance (Admin)")

    requests = storage.load("requests")
    donations = storage.load("donations")

    merged = requests.merge(
        donations[["donation_id", "donor_id", "donor_name", "food_name", "quantity_kg", "city", "status"]].rename(columns={"status": "donation_status"}),
        on="donation_id",
        how="left"
    )

    if not is_admin:
        merged = merged[merged["donor_id"] == user["user_id"]]

    pending = merged[merged["status"] == "Pending"]
    st.subheader(f"⏳ Pending Action Items ({len(pending)})")

    if pending.empty:
        st.info("No requests currently pending your review.")
    else:
        for row in pending.itertuples():
            with st.container(border=True):
                col_info, col_btns = st.columns([3, 2])
                with col_info:
                    st.write(f"🏢 **{row.recipient_name}** requested **{row.food_name}** ({row.quantity_kg} kg | {row.city})")
                    st.caption(f"Request ID: `{row.request_id}` &nbsp;|&nbsp; Submitted: `{row.requested_at}`")
                    if getattr(row, "message", None):
                        st.markdown(f"💬 *\"{row.message}\"*")

                with col_btns:
                    if row.donation_status != "Available":
                        st.warning(f"⚠️ Food item is currently in '{row.donation_status}' status.")
                    else:
                        if st.button("✅ Approve Request", key=f"appr_{row.request_id}", type="primary"):
                            approve_request(row.request_id, row.donation_id)
                            flash(f"✅ Request {row.request_id} approved! Listing reserved for {row.recipient_name}.")
                            st.rerun()

                        if st.button("❌ Reject Request", key=f"rej_{row.request_id}"):
                            storage.update_record("requests", row.request_id, {
                                "status": "Rejected",
                                "decided_at": storage.now_str()
                            })
                            flash(f"Request {row.request_id} rejected.", "warning")
                            st.rerun()

    # Request History
    st.divider()
    st.subheader("📜 Request History")
    history = merged[merged["status"] != "Pending"]
    if history.empty:
        st.caption("No historical requests recorded.")
    else:
        hist_cols = ["request_id", "donation_id", "food_name", "recipient_name", "status", "requested_at", "decided_at"]
        cols_to_show = [c for c in hist_cols if c in history.columns]
        st.dataframe(history[cols_to_show].sort_values("decided_at", ascending=False), use_container_width=True, hide_index=True)


# ==============================================================================
# 7. TWO-STEP DISTRIBUTION TRACKING (Collection -> Distribution)
# ==============================================================================

def track_distribution(user: Dict[str, Any]) -> None:
    """Track Approved pickups and record finalized meal distribution headcounts."""
    is_admin = user.get("role") == ROLE_ADMIN
    st.header("🚚 Collection & Distribution Tracking")
    st.caption("Coordinate physical pickup from donor facilities and log meal distributions to local communities.")

    requests = storage.load("requests")
    if not is_admin:
        requests = requests[requests["recipient_id"] == user["user_id"]]

    donations = storage.load("donations")[["donation_id", "food_name", "quantity_kg", "pickup_address", "city", "donor_name"]]
    merged = requests.merge(donations, on="donation_id", how="left")

    tab_pickup, tab_distribute, tab_history = st.tabs([
        "1. 📦 Approved (Awaiting Collection)",
        "2. 🍲 Collected (Awaiting Distribution)",
        "3. 📜 Completed Distribution Log"
    ])

    # TAB 1: PICKUP COORDINATION
    with tab_pickup:
        approved = merged[merged["status"] == "Approved"]
        if approved.empty:
            st.info("No approved donations awaiting pickup.")
        else:
            for row in approved.itertuples():
                with st.container(border=True):
                    c_left, c_right = st.columns([3, 2])
                    with c_left:
                        st.subheader(f"{row.food_name} ({row.quantity_kg} kg)")
                        st.write(f"**Donor:** {row.donor_name} &nbsp;|&nbsp; **City:** {row.city}")
                        st.markdown(f"📍 **Pickup Address:** `{row.pickup_address}`")
                        st.caption(f"Request ID: `{row.request_id}` &nbsp;|&nbsp; Recipient: `{row.recipient_name}`")
                    
                    with c_right:
                        st.markdown("**Confirm Collection:**")
                        if st.button("🚚 Confirm Food Collected", key=f"col_btn_{row.request_id}", type="primary"):
                            storage.add_record("distributions", {
                                "request_id": row.request_id,
                                "donation_id": row.donation_id,
                                "recipient_id": row.recipient_id,
                                "recipient_name": row.recipient_name,
                                "collected_at": storage.now_str(),
                                "distributed_at": "",
                                "people_served": 0,
                                "distribution_location": "",
                                "notes": "",
                                "status": "Collected",
                            })
                            storage.update_record("requests", row.request_id, {"status": "Collected"})
                            storage.update_record("donations", row.donation_id, {"status": "Collected"})
                            flash(f"Food item {row.food_name} collected! Proceed to Step 2 to record distribution.")
                            st.rerun()

    # TAB 2: MEAL DISTRIBUTION ENTRY
    with tab_distribute:
        collected = merged[merged["status"] == "Collected"]
        if collected.empty:
            st.info("No collected surplus food currently awaiting distribution logging.")
        else:
            for row in collected.itertuples():
                with st.container(border=True):
                    st.subheader(f"🍲 {row.food_name} ({row.quantity_kg} kg) — Request {row.request_id}")
                    with st.form(f"dist_form_{row.request_id}"):
                        c_p, c_l = st.columns(2)
                        people_served = c_p.number_input("Verified Beneficiaries (People Fed) *", min_value=1, max_value=50000, step=1, value=15)
                        dist_location = c_l.text_input("Distribution Site / Community Address *", placeholder="e.g. Hope Orphanage, Kukatpally Ward 4")
                        dist_notes = st.text_area("Distribution Notes", placeholder="e.g. Distributed hot lunch; packed meals distributed to families.")
                        submit_dist = st.form_submit_button("✨ Confirm Completed Distribution", type="primary")

                    if submit_dist:
                        val_errors = validate_distribution_entry(people_served, dist_location)
                        if val_errors:
                            for err in val_errors:
                                st.error(err)
                        else:
                            dists_df = storage.load("distributions")
                            matching_dists = dists_df[dists_df["request_id"] == row.request_id]
                            if matching_dists.empty:
                                st.error("Associated distribution record not found.")
                            else:
                                dist_id = matching_dists.iloc[0]["distribution_id"]
                                storage.update_record("distributions", dist_id, {
                                    "distributed_at": storage.now_str(),
                                    "people_served": int(people_served),
                                    "distribution_location": dist_location.strip(),
                                    "notes": dist_notes.strip(),
                                    "status": "Distributed",
                                })
                                storage.update_record("requests", row.request_id, {"status": "Distributed"})
                                storage.update_record("donations", row.donation_id, {"status": "Distributed"})
                                flash(f"🎉 Distribution successfully recorded! {people_served} people fed at {dist_location}.")
                                st.rerun()

    # TAB 3: DISTRIBUTION HISTORY LOG
    with tab_history:
        dists_df = storage.load("distributions")
        if not is_admin:
            dists_df = dists_df[dists_df["recipient_id"] == user["user_id"]]
        
        if dists_df.empty:
            st.info("No distribution records logged yet.")
        else:
            st.dataframe(dists_df, use_container_width=True, hide_index=True)
