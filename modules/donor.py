"""
================================================================================
MODULE: donor.py
MEMBER 1 DELIVERABLE: N Thulasi Krishna
================================================================================
Streamlit Interface & Food Donation Management Module.

Responsibilities:
1. Donor registration & session handling integration.
2. Donor Dashboard with personalized metrics, expiry alerts, and Plotly charts.
3. Add food donation form with multi-field validation (positive quantities,
   future expiration, dietary attributes, packaging details).
4. Edit and Delete donation records with referential integrity (cascading requests cleanup).
5. Comprehensive search, filtering, and sorting of donation listings.
6. Pure CSV persistence via utils.storage (strictly NO SQL).
================================================================================
"""

from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import plotly.express as px
import streamlit as st

from utils import storage
from utils.constants import CATEGORIES, DATE_FMT, DONATION_STATUSES
from utils.ui import flash

SHOW_COLUMNS = [
    "donation_id", "food_name", "category", "quantity_kg", "servings",
    "city", "expiry_datetime", "status", "created_at"
]

DIETARY_OPTIONS = [
    "Vegetarian", "Non-Vegetarian", "Vegan", "Halal Certified", "Eggless / Bakery", "Other"
]

PACKAGING_OPTIONS = [
    "Packed in sealed food-grade containers",
    "Packed in meal boxes",
    "Bulk catering containers",
    "Bakery trays / Bags",
    "Requires recipient to bring vessels"
]


# ==============================================================================
# 1. VALIDATION LOGIC (Decoupled for Unit Testing)
# ==============================================================================

def validate_donation(
    food_name: str,
    quantity: float,
    servings: int,
    city: str,
    address: str,
    expiry: datetime,
    category: Optional[str] = None
) -> List[str]:
    """
    Validate food donation input fields.
    Returns: List of error messages. Empty list [] means the form is valid.
    """
    errors: List[str] = []
    
    # 1. Food Name
    cleaned_name = str(food_name).strip()
    if len(cleaned_name) < 3:
        errors.append("Food item name must contain at least 3 characters.")
    elif len(cleaned_name) > 100:
        errors.append("Food item name cannot exceed 100 characters.")

    # 2. Category
    if category and category not in CATEGORIES:
        errors.append(f"Invalid category selected. Must be one of: {', '.join(CATEGORIES)}.")

    # 3. Numeric Physical Quantities
    try:
        qty_val = float(quantity)
        if qty_val <= 0.0:
            errors.append("Quantity must be greater than 0 kg.")
        elif qty_val > 5000.0:
            errors.append("Quantity exceeds maximum single listing limit (5,000 kg).")
    except (ValueError, TypeError):
        errors.append("Quantity must be a valid number.")

    try:
        srv_val = int(servings)
        if srv_val <= 0:
            errors.append("Number of servings must be at least 1 portion.")
        elif srv_val > 25000:
            errors.append("Servings cannot exceed 25,000 meals per entry.")
    except (ValueError, TypeError):
        errors.append("Servings must be a valid whole number.")

    # 4. Location Fields
    if not str(city).strip():
        errors.append("City / Region is required.")
        
    cleaned_address = str(address).strip()
    if len(cleaned_address) < 5:
        errors.append("Please provide a complete pickup address (at least 5 characters).")

    # 5. Temporal Constraints
    if not isinstance(expiry, datetime):
        errors.append("Invalid expiration date/time format.")
    else:
        now = datetime.now()
        if expiry <= now:
            errors.append(f"Best-before time must be in the future. (Current time: {now.strftime('%H:%M')}).")
        elif expiry > now + timedelta(days=30):
            errors.append("Perishable food donations cannot have an expiry date beyond 30 days.")

    return errors


def filter_donations_dataframe(
    df: pd.DataFrame,
    search_text: str = "",
    categories: Optional[List[str]] = None,
    cities: Optional[List[str]] = None,
    statuses: Optional[List[str]] = None,
    sort_by: str = "Newest First"
) -> pd.DataFrame:
    """
    Pure Pandas filter and search engine for donation records.
    Decoupled from Streamlit for clean unit testing.
    """
    if df.empty:
        return df.copy()

    res = df.copy()

    # 1. Text Search across food name, donor name, notes, and city
    if search_text and search_text.strip():
        query = search_text.strip().lower()
        search_corpus = (
            res["food_name"].fillna("").astype(str) + " " +
            res["donor_name"].fillna("").astype(str) + " " +
            res["notes"].fillna("").astype(str) + " " +
            res["city"].fillna("").astype(str)
        ).str.lower()
        res = res[search_corpus.str.contains(query, regex=False)]

    # 2. Categorical Filters
    if categories:
        res = res[res["category"].isin(categories)]
    if cities:
        res = res[res["city"].isin(cities)]
    if statuses:
        res = res[res["status"].isin(statuses)]

    # 3. Sorting Options
    if "created_at" in res.columns:
        if sort_by == "Newest First":
            res = res.sort_values("created_at", ascending=False)
        elif sort_by == "Oldest First":
            res = res.sort_values("created_at", ascending=True)
    if sort_by == "Quantity (Highest First)" and "quantity_kg" in res.columns:
        res["_tmp_qty"] = pd.to_numeric(res["quantity_kg"], errors="coerce").fillna(0)
        res = res.sort_values("_tmp_qty", ascending=False).drop(columns=["_tmp_qty"])
    elif sort_by == "Expiring Soonest" and "expiry_datetime" in res.columns:
        res["_tmp_exp"] = pd.to_datetime(res["expiry_datetime"], errors="coerce")
        res = res.sort_values("_tmp_exp", ascending=True).drop(columns=["_tmp_exp"])

    return res.reset_index(drop=True)


# ==============================================================================
# 2. DONOR DASHBOARD
# ==============================================================================

def donor_dashboard(user: Dict[str, Any]) -> None:
    """Render personalized donor analytics, active listings, and expiry status."""
    st.header(f"👋 Welcome, {user.get('name', 'Donor')}")
    st.caption(f"**Organisation:** {user.get('organization', 'Food Contributor')} &nbsp;|&nbsp; **City:** {user.get('city', 'Local Hub')}")
    
    donations = storage.load("donations")
    mine = donations[donations["donor_id"] == user["user_id"]].copy()

    if mine.empty:
        st.info("ℹ️ You haven't recorded any food donations yet. Click **Add Donation** in the menu to list your first surplus food!")
        return

    # Parse numeric values for metric cards
    mine["quantity_kg"] = pd.to_numeric(mine["quantity_kg"], errors="coerce").fillna(0.0)
    mine["servings"] = pd.to_numeric(mine["servings"], errors="coerce").fillna(0).astype(int)
    
    total_listed_kg = float(mine["quantity_kg"].sum())
    delivered_df = mine[mine["status"] == "Distributed"]
    expired_df = mine[mine["status"] == "Expired"]
    active_df = mine[mine["status"].isin(["Available", "Reserved"])]
    
    rescued_kg = float(delivered_df["quantity_kg"].sum())
    expired_kg = float(expired_df["quantity_kg"].sum())
    meals_delivered = int(delivered_df["servings"].sum())
    rescue_rate = round((rescued_kg / total_listed_kg * 100), 1) if total_listed_kg > 0 else 0.0

    # KPI Grid
    st.markdown("### 📊 My Contribution Summary")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📦 Total Donations", f"{len(mine)}")
    c2.metric("⚖️ Food Donated", f"{total_listed_kg:,.1f} kg")
    c3.metric("🍲 Meals Delivered", f"{meals_delivered:,} meals", f"{rescue_rate}% rescue rate")
    c4.metric("⏳ Active Listings", f"{len(active_df)}", help="Available or Reserved food items awaiting pickup")

    # Expiry Alert Banner
    now_dt = datetime.now()
    expiring_soon = []
    for _, row in active_df.iterrows():
        try:
            exp_time = datetime.strptime(row["expiry_datetime"], DATE_FMT)
            hours_left = (exp_time - now_dt).total_seconds() / 3600.0
            if 0 < hours_left <= 4.0:
                expiring_soon.append((row["food_name"], round(hours_left, 1), row["donation_id"]))
        except Exception:
            continue

    if expiring_soon:
        st.warning(f"⚠️ **Urgent Expiry Alert:** You have {len(expiring_soon)} active donation(s) expiring within 4 hours: " +
                   ", ".join([f"**{name}** ({hrs}h left - ID: {did})" for name, hrs, did in expiring_soon]))

    st.divider()

    # Visualizations
    left_col, right_col = st.columns(2)
    with left_col:
        st.markdown("#### Donations by Status")
        status_counts = mine["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        fig_status = px.pie(
            status_counts,
            names="status",
            values="count",
            hole=0.45,
            color="status",
            color_discrete_map={
                "Available": "#3B82F6",
                "Reserved": "#F59E0B",
                "Collected": "#8B5CF6",
                "Distributed": "#10B981",
                "Expired": "#EF4444"
            }
        )
        fig_status.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=True)
        st.plotly_chart(fig_status, use_container_width=True)

    with right_col:
        st.markdown("#### Food Donated by Category (kg)")
        cat_kg = mine.groupby("category", as_index=False)["quantity_kg"].sum().sort_values("quantity_kg", ascending=False)
        fig_cat = px.bar(
            cat_kg,
            x="category",
            y="quantity_kg",
            color="category",
            text_auto=".1f",
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        fig_cat.update_layout(xaxis_title="", yaxis_title="Kilograms (kg)", showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig_cat, use_container_width=True)

    st.subheader("📋 Recent Donation Activity")
    recent = mine.sort_values("created_at", ascending=False).head(5)
    cols_to_show = [c for c in SHOW_COLUMNS if c in recent.columns]
    st.dataframe(recent[cols_to_show], use_container_width=True, hide_index=True)


# ==============================================================================
# 3. ADD DONATION FORM (Validated)
# ==============================================================================

def add_donation(user: Dict[str, Any]) -> None:
    """Render validated food donation submission form."""
    st.header("➕ Register Surplus Food Donation")
    st.caption("Provide accurate details about available surplus food. Verified partner NGOs will browse and coordinate collection.")

    with st.form("add_donation_form", clear_on_submit=False):
        st.markdown("##### 1. Food Item Specifications")
        col1, col2 = st.columns(2)
        food_name = col1.text_input("Food Item Name *", placeholder="e.g. Mixed Vegetable Pulao & Paneer Curry")
        category = col2.selectbox("Food Category *", CATEGORIES)

        col3, col4 = st.columns(2)
        quantity = col3.number_input("Total Quantity (kg) *", min_value=0.1, max_value=5000.0, step=0.5, value=5.0)
        servings = col4.number_input("Estimated Portions / Servings *", min_value=1, max_value=25000, step=1, value=15)

        col5, col6 = st.columns(2)
        dietary = col5.selectbox("Dietary Classification", DIETARY_OPTIONS)
        packaging = col6.selectbox("Packaging / Handling Condition", PACKAGING_OPTIONS)

        st.markdown("##### 2. Pickup Location & Freshness Window")
        col7, col8 = st.columns(2)
        city = col7.text_input("City / Region *", value=user.get("city", "Hyderabad"))
        address = col8.text_input("Pickup Address with Landmark *", placeholder="e.g. Main Kitchen, 4th Floor, Skyline Towers, Banjara Hills")

        col9, col10 = st.columns(2)
        exp_date = col9.date_input("Best Before Date *", value=date.today())
        # Default best-before time: 6 hours from now
        default_exp_time = (datetime.now() + timedelta(hours=6)).time().replace(second=0, microsecond=0)
        exp_time = col10.time_input("Best Before Time (24h) *", value=default_exp_time)

        notes = st.text_area(
            "Special Instructions / Notes (Optional)",
            placeholder="e.g. Refrigerated since prep; contains milk products; please call 9876543210 upon arrival."
        )

        submitted = st.form_submit_button("🚀 Submit Donation Listing", type="primary")

    if submitted:
        expiry_dt = datetime.combine(exp_date, exp_time)
        
        # Combine notes with dietary and packaging details
        detailed_notes = f"[{dietary}] [{packaging}]"
        if notes and notes.strip():
            detailed_notes += f" {notes.strip()}"

        errors = validate_donation(
            food_name=food_name,
            quantity=quantity,
            servings=servings,
            city=city,
            address=address,
            expiry=expiry_dt,
            category=category
        )

        if errors:
            st.error("❌ **Please resolve the following validation issues:**")
            for err in errors:
                st.markdown(f"- {err}")
            return

        # Write to CSV storage
        new_id = storage.add_record("donations", {
            "donor_id": user["user_id"],
            "donor_name": user.get("name", "Donor"),
            "food_name": food_name.strip(),
            "category": category,
            "quantity_kg": round(float(quantity), 2),
            "servings": int(servings),
            "city": city.strip().title(),
            "pickup_address": address.strip(),
            "expiry_datetime": expiry_dt.strftime(DATE_FMT),
            "notes": detailed_notes,
            "status": "Available",
            "created_at": storage.now_str(),
        })

        st.success(f"🎉 **Donation Successfully Listed!** (Reference ID: **{new_id}**)")
        st.info("Local partner NGOs have been alerted and can now submit collection requests for this surplus food.")


# ==============================================================================
# 4. REUSABLE FILTERED DONATION CATALOG COMPONENT
# ==============================================================================

def donation_table_with_filters(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """Render interactive search, filter bar, and sorted donation table."""
    c1, c2, c3, c4, c5 = st.columns([1.5, 1, 1, 1, 1])
    search_q = c1.text_input("🔍 Search Food / Notes", key=f"{key}_search", placeholder="Type keyword...")
    selected_status = c2.multiselect("Status", DONATION_STATUSES, key=f"{key}_status")
    selected_cat = c3.multiselect("Category", CATEGORIES, key=f"{key}_cat")
    
    unique_cities = sorted([c for c in df["city"].dropna().unique() if c]) if "city" in df.columns else []
    selected_city = c4.multiselect("City", unique_cities, key=f"{key}_city")
    
    sort_option = c5.selectbox(
        "Sort By",
        ["Newest First", "Oldest First", "Quantity (Highest First)", "Expiring Soonest"],
        key=f"{key}_sort"
    )

    filtered = filter_donations_dataframe(
        df,
        search_text=search_q,
        categories=selected_cat,
        cities=selected_city,
        statuses=selected_status,
        sort_by=sort_option
    )

    st.caption(f"Showing **{len(filtered)}** of **{len(df)}** donation records")
    
    display_cols = [c for c in SHOW_COLUMNS + ["donor_name", "notes"] if c in filtered.columns]
    st.dataframe(filtered[display_cols], use_container_width=True, hide_index=True)
    return filtered


# ==============================================================================
# 5. MY DONATIONS (EDIT & DELETE WITH INTEGRITY)
# ==============================================================================

def my_donations(user: Dict[str, Any]) -> None:
    """Donor donation catalog with full Edit and Safe Delete functionality."""
    st.header("📦 Manage My Food Donations")
    donations = storage.load("donations")
    mine = donations[donations["donor_id"] == user["user_id"]]

    if mine.empty:
        st.info("You haven't added any donations yet.")
        return

    # View catalog with search/filter
    donation_table_with_filters(mine, key="my_donations_view")

    st.divider()
    st.subheader("✏️ Edit or Remove a Listing")
    st.caption("Donation listings can only be edited or removed while in **Available** status (before an NGO request is approved).")

    editable = mine[mine["status"] == "Available"].copy()
    if editable.empty:
        st.info("💡 You currently have no listings in 'Available' status to modify.")
        return

    # Dropdown selector
    labels = {
        row.donation_id: f"{row.donation_id} — {row.food_name} ({row.quantity_kg} kg | Expiry: {row.expiry_datetime})"
        for row in editable.itertuples()
    }
    selected_id = st.selectbox("Select Donation to Modify", list(labels.keys()), format_func=lambda x: labels[x])
    record = storage.get_record("donations", selected_id)

    if not record:
        st.error("Selected record could not be loaded.")
        return

    tab_edit, tab_delete = st.tabs(["📝 Edit Details", "🗑️ Delete Listing"])

    # TAB: EDIT
    with tab_edit:
        with st.form(f"edit_form_{selected_id}"):
            c_e1, c_e2 = st.columns(2)
            e_food_name = c_e1.text_input("Food Item Name *", value=record.get("food_name", ""))
            
            cat_idx = CATEGORIES.index(record["category"]) if record.get("category") in CATEGORIES else 0
            e_category = c_e2.selectbox("Category *", CATEGORIES, index=cat_idx)

            c_e3, c_e4 = st.columns(2)
            e_quantity = c_e3.number_input(
                "Quantity (kg) *",
                min_value=0.1,
                max_value=5000.0,
                step=0.5,
                value=float(record.get("quantity_kg") or 1.0)
            )
            e_servings = c_e4.number_input(
                "Servings *",
                min_value=1,
                max_value=25000,
                step=1,
                value=int(float(record.get("servings") or 10))
            )

            c_e5, c_e6 = st.columns(2)
            e_city = c_e5.text_input("City *", value=record.get("city", ""))
            e_address = c_e6.text_input("Pickup Address *", value=record.get("pickup_address", ""))

            # Date / Time
            try:
                old_exp_dt = datetime.strptime(record["expiry_datetime"], DATE_FMT)
            except Exception:
                old_exp_dt = datetime.now() + timedelta(hours=6)

            c_e7, c_e8 = st.columns(2)
            e_exp_date = c_e7.date_input("Best Before Date *", value=old_exp_dt.date())
            e_exp_time = c_e8.time_input("Best Before Time *", value=old_exp_dt.time())

            e_notes = st.text_area("Notes", value=record.get("notes", ""))
            save_changes = st.form_submit_button("💾 Save Updates", type="primary")

        if save_changes:
            new_exp_dt = datetime.combine(e_exp_date, e_exp_time)
            edit_errors = validate_donation(
                food_name=e_food_name,
                quantity=e_quantity,
                servings=e_servings,
                city=e_city,
                address=e_address,
                expiry=new_exp_dt,
                category=e_category
            )

            if edit_errors:
                for err in edit_errors:
                    st.error(err)
            else:
                storage.update_record("donations", selected_id, {
                    "food_name": e_food_name.strip(),
                    "category": e_category,
                    "quantity_kg": round(float(e_quantity), 2),
                    "servings": int(e_servings),
                    "city": e_city.strip().title(),
                    "pickup_address": e_address.strip(),
                    "expiry_datetime": new_exp_dt.strftime(DATE_FMT),
                    "notes": e_notes.strip()
                })
                flash(f"✅ Donation listing {selected_id} updated successfully.")
                st.rerun()

    # TAB: DELETE
    with tab_delete:
        st.warning(f"⚠️ You are about to permanently delete **{selected_id}** (*{record.get('food_name')}*). This action cannot be undone.")
        confirm_check = st.checkbox(f"I confirm that I wish to remove listing {selected_id}", key=f"confirm_del_{selected_id}")
        
        if st.button("🗑️ Confirm Permanent Delete", type="primary", disabled=not confirm_check):
            # 1. Delete from donations.csv
            storage.delete_record("donations", selected_id)
            
            # 2. Cascading cleanup: delete any pending requests attached to this donation
            requests_df = storage.load("requests")
            if not requests_df.empty and "donation_id" in requests_df.columns:
                attached_requests = requests_df[requests_df["donation_id"] == selected_id]
                for rid in attached_requests["request_id"]:
                    storage.delete_record("requests", rid)

            flash(f"🗑️ Donation {selected_id} and its associated requests were safely deleted.")
            st.rerun()
