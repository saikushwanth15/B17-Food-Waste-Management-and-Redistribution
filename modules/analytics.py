"""
================================================================================
MODULE: analytics.py
MEMBER 3 DELIVERABLE: L Sai Kushwanth
================================================================================
Streamlit Interactive Analytics Dashboard & Visualization Engine using Plotly.

Features:
1. Executive KPI cards with clean typography and units.
2. Filter controls for Date range, Category, and City.
3. Interactive Plotly charts:
   - Bar chart: Category breakdown
   - Line chart & Area chart: Temporal donation & waste trends
   - Grouped Bar chart: Listed vs Rescued by City
   - Heatmap: Category x City cross-tabulation
   - Donut charts: Status and Category distributions
   - Horizontal Bar charts: Top Donors & NGO Beneficiaries
   - Histogram: Kilogram quantity distribution
4. Kaggle & External Waste Dataset Explorer:
   - Ingests university canteen & restaurant datasets or user uploads
   - Auto-detection of Date, Category, Waste, and Location columns
   - Manual dropdown fallbacks if automatic detection misses
   - Data hygiene metrics (rows before, duplicates, dropped negatives, imputed)
   - PDF audit report download for the analyzed dataset
5. In-Memory ReportLab PDF Report Downloads & Cleaned CSV exports.
================================================================================
"""

import glob
import os
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from modules import analysis, reports
from utils import storage

WASTE_DIR = os.path.join(storage.DATA_DIR, "waste_datasets")


# ------------------------------------------------------------------------------
# KPI DISPLAY COMPONENT
# ------------------------------------------------------------------------------

def _render_kpi_grid(kpis: Dict[str, Any]) -> None:
    """Render structured responsive KPI cards."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📦 Food Listed", f"{kpis.get('Total food listed (kg)', 0):,.1f} kg", help="Total food registered by donors")
    c2.metric("✨ Food Rescued", f"{kpis.get('Food rescued & distributed (kg)', 0):,.1f} kg", f"{kpis.get('Rescue rate (%)', 0)}% rate")
    c3.metric("⚠️ Food Expired", f"{kpis.get('Food expired / wasted (kg)', 0):,.1f} kg", f"-{kpis.get('Wastage rate (%)', 0)}% lost", delta_color="inverse")
    c4.metric("👥 People Fed", f"{kpis.get('People served', 0):,}", f"{kpis.get('Meals delivered', 0):,} meals")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("📋 Total Donations", f"{kpis.get('Total donations', 0):,}")
    c6.metric("⏱️ Avg. Turnaround", f"{kpis.get('Avg. response time (hours)', 0)} hrs")
    c7.metric("🏪 Active Donors", f"{kpis.get('Active donors', 0)}")
    c8.metric("🤝 Partner NGOs", f"{kpis.get('Active NGOs', 0)}")


# ------------------------------------------------------------------------------
# MAIN STREAMLIT ANALYTICS DASHBOARD
# ------------------------------------------------------------------------------

def analytics_dashboard() -> None:
    """Render the primary interactive Analytics Dashboard."""
    st.title("📊 Food Waste & Redistribution Analytics")
    st.markdown(
        "Welcome to the **Analytics & Operational Intelligence Dashboard** supporting **SDG 2: Zero Hunger**. "
        "Here you can explore live donation redistribution patterns, track rescue efficiencies, "
        "and analyze historical canteen and restaurant food-waste datasets."
    )

    donations_all, requests_all, dists_all = analysis.load_clean_data()

    tab_overview, tab_trends, tab_geo_cat, tab_distribution, tab_waste_explorer = st.tabs([
        "📈 Live Overview",
        "📅 Redistribution Trends",
        "🥗 Categories & Cities",
        "🚚 Requests & Stakeholders",
        "🔬 Historical Waste Datasets (Kaggle)"
    ])

    # Tab 5: Kaggle Datasets Explorer (accessible even if live data is empty)
    with tab_waste_explorer:
        waste_dataset_analysis()

    if donations_all.empty:
        for t in [tab_overview, tab_trends, tab_geo_cat, tab_distribution]:
            with t:
                st.info("ℹ️ No live donation data found. Please add donations or run `python seed_data.py` to view live analytics.")
        return

    # --------------------------------------------------------------------------
    # Interactive Live Filters in Sidebar or Top Expander
    # --------------------------------------------------------------------------
    with st.expander("🔍 Filter Operational Data", expanded=False):
        f_col1, f_col2, f_col3 = st.columns(3)
        
        # Category Filter
        available_categories = sorted(list(donations_all["category"].dropna().unique()))
        selected_cats = f_col1.multiselect("Food Category", available_categories, default=available_categories)
        
        # City Filter
        available_cities = sorted(list(donations_all["city"].dropna().unique()))
        selected_cities = f_col2.multiselect("City / Region", available_cities, default=available_cities)
        
        # Status Filter
        available_statuses = sorted(list(donations_all["status"].dropna().unique()))
        selected_statuses = f_col3.multiselect("Donation Status", available_statuses, default=available_statuses)

    # Apply filters
    filtered_donations = donations_all[
        donations_all["category"].isin(selected_cats if selected_cats else available_categories) &
        donations_all["city"].isin(selected_cities if selected_cities else available_cities) &
        donations_all["status"].isin(selected_statuses if selected_statuses else available_statuses)
    ].copy()

    if filtered_donations.empty:
        st.warning("⚠️ No records match the selected filter criteria. Please adjust your filters.")
        return

    live_kpis = analysis.compute_kpis(filtered_donations, requests_all, dists_all)

    # --------------------------------------------------------------------------
    # TAB 1: OVERVIEW & FLOW
    # --------------------------------------------------------------------------
    with tab_overview:
        st.subheader("Operational Key Performance Indicators")
        _render_kpi_grid(live_kpis)
        st.divider()

        col_pie, col_bar = st.columns([1, 1.2])
        
        with col_pie:
            st.markdown("#### Donation Status Breakdown")
            status_df = analysis.by_status(filtered_donations)
            fig_status = px.pie(
                status_df,
                names="status",
                values="donations",
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
            fig_status.update_traces(textposition="inside", textinfo="percent+label")
            fig_status.update_layout(showlegend=False, margin=dict(t=20, b=20, l=10, r=10))
            st.plotly_chart(fig_status, use_container_width=True)

        with col_bar:
            st.markdown("#### Surplus Food Allocation (kg)")
            outcome_df = pd.DataFrame({
                "Outcome": ["Rescued & Distributed", "Expired / Wasted", "In Active Pipeline"],
                "Kilograms": [
                    live_kpis["Food rescued & distributed (kg)"],
                    live_kpis["Food expired / wasted (kg)"],
                    live_kpis["Food in redistribution pipeline (kg)"]
                ],
                "Color": ["#10B981", "#EF4444", "#3B82F6"]
            })
            fig_outcome = px.bar(
                outcome_df,
                x="Outcome",
                y="Kilograms",
                color="Outcome",
                text_auto=".1f",
                color_discrete_map={
                    "Rescued & Distributed": "#10B981",
                    "Expired / Wasted": "#EF4444",
                    "In Active Pipeline": "#3B82F6"
                }
            )
            fig_outcome.update_layout(xaxis_title="", yaxis_title="Kilograms (kg)", showlegend=False, margin=dict(t=20, b=20))
            st.plotly_chart(fig_outcome, use_container_width=True)

        # Quantity Histogram
        st.markdown("#### Distribution of Donation Sizes (kg)")
        fig_hist = px.histogram(
            filtered_donations,
            x="quantity_kg",
            nbins=25,
            color_discrete_sequence=["#2E7D32"],
            marginal="box",
            title="Histogram: Quantity per Donation (kg)"
        )
        fig_hist.update_layout(xaxis_title="Donation Quantity (kg)", yaxis_title="Count of Donations")
        st.plotly_chart(fig_hist, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 2: TEMPORAL TRENDS
    # --------------------------------------------------------------------------
    with tab_trends:
        st.subheader("Monthly & Daily Redistribution Trajectory")
        
        m_trend = analysis.monthly_trend(filtered_donations)
        if not m_trend.empty:
            c_line, c_bar = st.columns(2)
            with c_line:
                fig_m_line = px.line(
                    m_trend,
                    x="month",
                    y="food_kg",
                    markers=True,
                    line_shape="spline",
                    title="Monthly Food Listed (kg)",
                    color_discrete_sequence=["#1B5E20"]
                )
                fig_m_line.update_layout(xaxis_title="Month", yaxis_title="Weight (kg)")
                st.plotly_chart(fig_m_line, use_container_width=True)

            with c_bar:
                fig_m_bar = px.bar(
                    m_trend,
                    x="month",
                    y="donations",
                    text_auto=True,
                    title="Monthly Number of Donation Records",
                    color_discrete_sequence=["#4CAF50"]
                )
                fig_m_bar.update_layout(xaxis_title="Month", yaxis_title="Number of Records")
                st.plotly_chart(fig_m_bar, use_container_width=True)

        d_trend = analysis.daily_trend(filtered_donations)
        if not d_trend.empty:
            st.markdown("#### Daily Volume Stream (kg)")
            fig_area = px.area(
                d_trend,
                x="date",
                y="quantity_kg",
                title="Daily Food Volume Registered (kg)",
                color_discrete_sequence=["#81C784"]
            )
            fig_area.update_layout(xaxis_title="Date", yaxis_title="Kilograms (kg)")
            st.plotly_chart(fig_area, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 3: CATEGORIES & GEOGRAPHY
    # --------------------------------------------------------------------------
    with tab_geo_cat:
        st.subheader("Category Distribution & Geographic Insights")
        
        cat_df = analysis.by_category(filtered_donations)
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            fig_cat_bar = px.bar(
                cat_df,
                x="category",
                y="food_kg",
                color="category",
                text_auto=".1f",
                title="Food Surplus Volume by Category (kg)"
            )
            fig_cat_bar.update_layout(xaxis_title="Category", yaxis_title="Total Kilograms", showlegend=False)
            st.plotly_chart(fig_cat_bar, use_container_width=True)

        with col_c2:
            fig_cat_pie = px.pie(
                cat_df,
                names="category",
                values="donations",
                title="Proportion of Donation Records by Category",
                hole=0.4
            )
            st.plotly_chart(fig_cat_pie, use_container_width=True)

        st.divider()
        st.subheader("Geographical Rescue Efficiency (by City)")
        city_df = analysis.by_city(filtered_donations)
        if not city_df.empty:
            fig_city = px.bar(
                city_df,
                x="city",
                y=["food_kg", "rescued_kg"],
                barmode="group",
                title="Listed Surplus vs Rescued Food by City (kg)",
                labels={"value": "Kilograms (kg)", "variable": "Metric"},
                color_discrete_map={"food_kg": "#9E9E9E", "rescued_kg": "#2E7D32"}
            )
            st.plotly_chart(fig_city, use_container_width=True)

        # Cross-tab heatmap
        st.markdown("#### Regional Food Type Heatmap")
        pivot_mat = analysis.category_city_pivot(filtered_donations)
        if not pivot_mat.empty:
            fig_heat = px.imshow(
                pivot_mat,
                aspect="auto",
                color_continuous_scale="Greens",
                text_auto=".1f",
                title="Heatmap: Food Weight (kg) by City and Category"
            )
            fig_heat.update_layout(xaxis_title="Category", yaxis_title="City")
            st.plotly_chart(fig_heat, use_container_width=True)

    # --------------------------------------------------------------------------
    # TAB 4: REQUESTS & DISTRIBUTION
    # --------------------------------------------------------------------------
    with tab_distribution:
        st.subheader("NGO Request Flow & Stakeholder Recognition")
        
        c_req, c_donor = st.columns(2)
        with c_req:
            st.markdown("#### NGO Requests by Status")
            if requests_all.empty:
                st.info("No request records logged yet.")
            else:
                req_counts = requests_all["status"].value_counts().reset_index()
                req_counts.columns = ["status", "requests"]
                fig_req = px.bar(
                    req_counts,
                    x="status",
                    y="requests",
                    color="status",
                    text_auto=True,
                    color_discrete_map={
                        "Pending": "#F59E0B",
                        "Approved": "#10B981",
                        "Rejected": "#EF4444"
                    }
                )
                fig_req.update_layout(xaxis_title="Status", yaxis_title="Requests Count", showlegend=False)
                st.plotly_chart(fig_req, use_container_width=True)

        with c_donor:
            st.markdown("#### Top Food Contributors")
            top_d = analysis.top_donors(filtered_donations, n=6)
            if not top_d.empty:
                fig_donors = px.bar(
                    top_d,
                    x="food_kg",
                    y="donor_name",
                    orientation="h",
                    text_auto=".1f",
                    title="Top Donors by Total Weight (kg)",
                    color_discrete_sequence=["#1B5E20"]
                )
                fig_donors.update_layout(xaxis_title="Weight Contributed (kg)", yaxis_title="Donor")
                st.plotly_chart(fig_donors, use_container_width=True)

        # Top NGOs by Beneficiaries
        st.markdown("#### Beneficiary Impact by Partner NGO")
        top_n = analysis.top_ngos(dists_all, n=6)
        if top_n.empty:
            st.info("No completed NGO distributions recorded yet.")
        else:
            fig_ngos = px.bar(
                top_n,
                x="people_served",
                y="recipient_name",
                orientation="h",
                text_auto=True,
                title="Recorded Beneficiaries Served by NGO",
                color_discrete_sequence=["#00897B"]
            )
            fig_ngos.update_layout(xaxis_title="Number of Beneficiaries", yaxis_title="NGO Name")
            st.plotly_chart(fig_ngos, use_container_width=True)


# ==============================================================================
# KAGGLE & EXTERNAL FOOD WASTE DATASET AUDIT COMPONENT
# ==============================================================================

def waste_dataset_analysis() -> None:
    """
    Dedicated explorer for university canteen and restaurant food waste datasets.
    Supports auto-column discovery and user manual column selection override.
    """
    st.subheader("🔬 Historical Food-Waste Dataset Explorer")
    st.markdown(
        "Analyze real-world Kaggle datasets (*University Canteen Food Waste* & *Restaurant Wastage*). "
        "These historical records identify pattern drivers and help institutions avoid food waste before it occurs."
    )

    available_files = sorted(glob.glob(os.path.join(WASTE_DIR, "*.csv")))
    file_options = [os.path.basename(f) for f in available_files]
    file_options.append("📤 Upload Custom Kaggle / Institutional CSV...")

    selection = st.selectbox("Select Dataset to Inspect", file_options)

    if selection == "📤 Upload Custom Kaggle / Institutional CSV...":
        uploaded_file = st.file_uploader("Upload a Food Waste CSV file", type=["csv"])
        if uploaded_file is None:
            st.info("Please upload a CSV file to begin analysis.")
            return
        dataset_name = uploaded_file.name
        try:
            raw_df = pd.read_csv(uploaded_file)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
            return
    else:
        dataset_name = selection
        raw_df = pd.read_csv(os.path.join(WASTE_DIR, selection))

    if raw_df.empty:
        st.error("The selected CSV file contains zero rows.")
        return

    # Auto-detection
    detected_schema = analysis.auto_detect_dataset_schema(raw_df)
    
    with st.expander("🛠️ Column Mapping & Hygiene Configuration", expanded=False):
        st.caption("Auto-detection attempted. If a column was not correctly identified, select it manually below:")
        col_list = ["(None)"] + list(raw_df.columns)
        
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        
        idx_waste = col_list.index(detected_schema["waste_col"]) if detected_schema["waste_col"] in col_list else 0
        idx_cat = col_list.index(detected_schema["category_col"]) if detected_schema["category_col"] in col_list else 0
        idx_date = col_list.index(detected_schema["date_col"]) if detected_schema["date_col"] in col_list else 0
        idx_loc = col_list.index(detected_schema["location_col"]) if detected_schema["location_col"] in col_list else 0
        
        selected_waste = col_c1.selectbox("Waste Quantity Column *", col_list, index=idx_waste)
        selected_cat = col_c2.selectbox("Food Category Column", col_list, index=idx_cat)
        selected_date = col_c3.selectbox("Date / Timestamp Column", col_list, index=idx_date)
        selected_loc = col_c4.selectbox("Location / Unit Column", col_list, index=idx_loc)

    waste_col_name = None if selected_waste == "(None)" else selected_waste
    cat_col_name = None if selected_cat == "(None)" else selected_cat
    date_col_name = None if selected_date == "(None)" else selected_date
    loc_col_name = None if selected_loc == "(None)" else selected_loc

    # Run Data Cleaning Pipeline
    cleaned_df, audit_report = analysis.clean_waste_dataset(
        raw_df,
        date_col=date_col_name,
        waste_col=waste_col_name,
        category_col=cat_col_name,
        location_col=loc_col_name
    )

    # Display Data Hygiene Audit Metrics
    st.markdown("#### 🧼 Data Cleaning & Hygiene Audit")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Rows Loaded", f"{audit_report['rows_before']:,}")
    m2.metric("Duplicates Dropped", f"{audit_report['duplicates_removed']:,}")
    m3.metric("Negatives Filtered", f"{audit_report['negative_dropped']:,}")
    m4.metric("Missing Imputed", f"{audit_report['missing_imputed']:,}")
    m5.metric("Usable Rows", f"{audit_report['rows_after']:,}")

    # Statistical Overview if Waste Column Present
    effective_waste_col = audit_report.get("waste_col")
    waste_metrics = {}
    if effective_waste_col and effective_waste_col in cleaned_df.columns:
        waste_metrics = analysis.compute_waste_metrics(cleaned_df, effective_waste_col)
        st.markdown("#### ⚖️ Waste Statistics Overview")
        w1, w2, w3, w4 = st.columns(4)
        w1.metric("Total Food Waste", f"{waste_metrics['total_waste_kg']:,.1f} kg")
        w2.metric("Mean Waste / Observation", f"{waste_metrics['avg_waste_kg']:.2f} kg")
        w3.metric("Median Waste", f"{waste_metrics['median_waste_kg']:.2f} kg")
        w4.metric("Peak Waste", f"{waste_metrics['max_waste_kg']:.2f} kg")

    # Visualizations
    st.markdown("#### 📊 Exploratory Visualizations")
    numeric_columns = list(cleaned_df.select_dtypes(include=[np.number]).columns)
    text_columns = [c for c in cleaned_df.columns if cleaned_df[c].dtype == "object" and cleaned_df[c].nunique() <= 35]
    date_columns = [c for c in cleaned_df.columns if pd.api.types.is_datetime64_any_dtype(cleaned_df[c])]

    chart_c1, chart_c2 = st.columns(2)
    
    # 1. Bar Chart: Categorical grouping
    with chart_c1:
        if numeric_columns and text_columns:
            val_col = st.selectbox("Numeric Metric to Plot", numeric_columns, index=numeric_columns.index(effective_waste_col) if effective_waste_col in numeric_columns else 0)
            grp_col = st.selectbox("Category Dimension", text_columns, index=0)
            grouped_agg = cleaned_df.groupby(grp_col, as_index=False)[val_col].sum().sort_values(val_col, ascending=False)
            fig_grp = px.bar(
                grouped_agg,
                x=grp_col,
                y=val_col,
                color=grp_col,
                title=f"{val_col} by {grp_col}",
                text_auto=".1f"
            )
            fig_grp.update_layout(showlegend=False)
            st.plotly_chart(fig_grp, use_container_width=True)

    # 2. Histogram: Waste Distribution
    with chart_c2:
        if effective_waste_col and effective_waste_col in cleaned_df.columns:
            fig_hist = px.histogram(
                cleaned_df,
                x=effective_waste_col,
                nbins=25,
                marginal="box",
                title=f"Distribution of {effective_waste_col}",
                color_discrete_sequence=["#D32F2F"]
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        elif numeric_columns:
            fig_hist = px.histogram(
                cleaned_df,
                x=numeric_columns[0],
                nbins=25,
                title=f"Distribution of {numeric_columns[0]}",
                color_discrete_sequence=["#D32F2F"]
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    # 3. Time Series Line Chart if Date Present
    if date_columns and numeric_columns:
        dt_col = date_columns[0]
        val_time_col = effective_waste_col if effective_waste_col else numeric_columns[0]
        time_series = cleaned_df.groupby(dt_col, as_index=False)[val_time_col].sum().sort_values(dt_col)
        fig_time = px.line(
            time_series,
            x=dt_col,
            y=val_time_col,
            markers=True,
            title=f"Timeline Trend: {val_time_col} over Time",
            color_discrete_sequence=["#E65100"]
        )
        st.plotly_chart(fig_time, use_container_width=True)

    # 4. Correlation Heatmap if 2+ numeric columns
    if len(numeric_columns) >= 2:
        with st.expander("🔢 Feature Correlation Matrix", expanded=False):
            corr = cleaned_df[numeric_columns].corr()
            fig_corr = px.imshow(
                corr,
                text_auto=".2f",
                color_continuous_scale="RdYlGn",
                title="Correlation Heatmap between Numeric Variables"
            )
            st.plotly_chart(fig_corr, use_container_width=True)

    # Data Preview & Summary Statistics
    with st.expander("📋 Cleaned Data Preview & Statistical Summary", expanded=False):
        st.dataframe(cleaned_df.head(25), use_container_width=True, hide_index=True)
        st.markdown("**Descriptive Statistics:**")
        st.dataframe(cleaned_df.describe(), use_container_width=True)

    # Export & PDF Download for Dataset
    st.divider()
    exp_c1, exp_c2 = st.columns(2)
    
    exp_c1.download_button(
        label=f"💾 Download Cleaned {dataset_name}",
        data=cleaned_df.to_csv(index=False),
        file_name=f"cleaned_{dataset_name}",
        mime="text/csv",
        key=f"dl_clean_{dataset_name}"
    )

    cat_summary_table = None
    if text_columns and effective_waste_col:
        cat_summary_table = cleaned_df.groupby(text_columns[0], as_index=False)[effective_waste_col].agg(["count", "sum"]).reset_index()
        cat_summary_table.columns = ["Category", "Observations", "Total Waste (kg)"]

    audit_pdf_bytes = reports.build_waste_dataset_report(
        dataset_name=dataset_name,
        cleaning_report=audit_report,
        waste_metrics=waste_metrics,
        category_summary=cat_summary_table
    )
    
    exp_c2.download_button(
        label="📑 Download Historical Waste Audit Report (PDF)",
        data=audit_pdf_bytes,
        file_name=f"waste_audit_{dataset_name}.pdf",
        mime="application/pdf",
        type="primary",
        key=f"dl_pdf_{dataset_name}"
    )


# ==============================================================================
# DOWNLOADS & REPORTS HUB SCREEN
# ==============================================================================

def reports_page() -> None:
    """Dedicated screen for downloading PDF Reports and CSV backups."""
    st.title("📑 Reports & Data Export Center")
    st.markdown(
        "Download professional **ReportLab PDF documents** synthesized dynamically from current "
        "application records, or export cleaned operational CSV files."
    )

    donations_all, requests_all, dists_all = analysis.load_clean_data()
    live_kpis = analysis.compute_kpis(donations_all, requests_all, dists_all)

    st.subheader("1. Formal PDF Impact Reports")
    r1, r2 = st.columns(2)

    with r1:
        st.markdown("#### 📈 Operational Analytics Report")
        st.caption("Detailed executive report with KPI tables, category charts, geographic breakdown, and automated findings.")
        analytics_pdf = reports.build_analytics_report(
            kpis=live_kpis,
            monthly=analysis.monthly_trend(donations_all),
            categories=analysis.by_category(donations_all),
            cities=analysis.by_city(donations_all),
            statuses=analysis.by_status(donations_all),
            donors=analysis.top_donors(donations_all),
            ngos=analysis.top_ngos(dists_all)
        )
        st.download_button(
            label="📥 Download Executive Analytics Report (PDF)",
            data=analytics_pdf,
            file_name="Food_Rescue_Executive_Analytics_Report.pdf",
            mime="application/pdf",
            type="primary"
        )

    with r2:
        st.markdown("#### 🎓 Project Evaluation & Viva Summary")
        st.caption("College evaluation document detailing SDG 2 alignment, Member responsibilities, and architecture.")
        eval_pdf = reports.build_evaluation_summary(live_kpis)
        st.download_button(
            label="📥 Download Semester Viva Summary (PDF)",
            data=eval_pdf,
            file_name="Food_Rescue_Evaluation_Viva_Summary.pdf",
            mime="application/pdf"
        )

    st.divider()
    st.subheader("2. Operational CSV Data Export")
    st.caption("Export pure flat CSV files for external verification (Strictly CSV storage, No SQL databases).")

    csv_cols = st.columns(3)
    for idx, table_name in enumerate(["donations", "requests", "distributions"]):
        tbl_df = storage.load(table_name)
        with csv_cols[idx]:
            st.download_button(
                label=f"💾 Export {table_name}.csv ({len(tbl_df)} rows)",
                data=tbl_df.to_csv(index=False),
                file_name=f"{table_name}.csv",
                mime="text/csv",
                key=f"export_{table_name}"
            )

    st.divider()
    st.subheader("3. Live System KPI Summary Table")
    kpi_table_df = pd.DataFrame({
        "Performance Indicator": list(live_kpis.keys()),
        "Computed Value": list(live_kpis.values())
    })
    st.dataframe(kpi_table_df, use_container_width=True, hide_index=True)
