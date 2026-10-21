"""
================================================================================
MODULE: analysis.py
MEMBER 3 DELIVERABLE: L Sai Kushwanth
================================================================================
Pure Python & Pandas data processing, KPI calculation, and statistical aggregation
layer for the Food Waste Management and Redistribution platform (SDG 2 - Zero Hunger).

Strict Architecture Rules:
- ZERO Streamlit imports: Decoupled for clean unit testing and PDF generation.
- Pure Pandas & CSV: Absolutely NO SQL / SQLite / MySQL databases.
- Defensive: Safe division-by-zero, missing value handling, empty dataframe handling.
- Separation of Concerns: Historical waste datasets are kept completely separate
  from operational live donation and distribution records.
================================================================================
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import re

from utils import storage

# Finalized or active workflow states in live application
COMPLETED_STATUSES = ["Approved", "Collected", "Distributed"]


# ==============================================================================
# 1. LIVE OPERATIONAL DATA CLEANING (Donations, Requests, Distributions)
# ==============================================================================

def clean_donations(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and normalize live food donation records from donations.csv.
    
    Steps performed:
    1. Coerce quantity_kg and servings to numeric floats/ints.
    2. Parse creation timestamp and expiration timestamp to Datetime.
    3. Title-case and strip string fields (category, city, status).
    4. Deduplicate rows based on donation_id.
    5. Drop records missing vital fields (quantity_kg <= 0 or NaT timestamps).
    6. Extract derived calendar attributes (month 'YYYY-MM', date 'YYYY-MM-DD').
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "donation_id", "donor_id", "donor_name", "food_name", "category",
            "quantity_kg", "servings", "city", "pickup_address", "expiry_datetime",
            "notes", "status", "created_at", "month", "date"
        ])

    df = df.copy()
    
    # 1. Safe numeric conversion
    if "quantity_kg" in df.columns:
        df["quantity_kg"] = pd.to_numeric(df["quantity_kg"], errors="coerce")
    if "servings" in df.columns:
        df["servings"] = pd.to_numeric(df["servings"], errors="coerce").fillna(0).astype(int)
    
    # 2. Date/time parsing
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    if "expiry_datetime" in df.columns:
        df["expiry_datetime"] = pd.to_datetime(df["expiry_datetime"], errors="coerce")
    
    # 3. String normalization
    for col in ["category", "city", "status", "donor_name", "food_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title().replace({"": "Unknown", "Nan": "Unknown"})
            
    # 4. Deduplication
    if "donation_id" in df.columns:
        df = df.drop_duplicates(subset=["donation_id"])
    else:
        df = df.drop_duplicates()
        
    # 5. Filter out unusable or unphysical records
    filter_cols = [c for c in ["quantity_kg", "created_at"] if c in df.columns]
    if filter_cols:
        df = df.dropna(subset=filter_cols)
    if "quantity_kg" in df.columns:
        df = df[df["quantity_kg"] > 0]
    
    # 6. Calendar derived fields
    if "created_at" in df.columns:
        df["month"] = df["created_at"].dt.to_period("M").astype(str)
        df["date"] = df["created_at"].dt.normalize()
    else:
        df["month"] = "Unknown"
        df["date"] = pd.NaT
    
    return df.reset_index(drop=True)


def clean_requests(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and parse NGO food request records from requests.csv.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "request_id", "donation_id", "recipient_id", "recipient_name",
            "message", "status", "requested_at", "decided_at"
        ])

    df = df.copy()
    df["requested_at"] = pd.to_datetime(df["requested_at"], errors="coerce")
    df["decided_at"] = pd.to_datetime(df["decided_at"], errors="coerce")
    
    for col in ["status", "recipient_name"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title().replace({"": "Unknown", "Nan": "Unknown"})
            
    if "request_id" in df.columns:
        df = df.drop_duplicates(subset=["request_id"])
    else:
        df = df.drop_duplicates()
        
    return df.reset_index(drop=True)


def clean_distributions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and parse completed food distribution records from distributions.csv.
    """
    if df.empty:
        return pd.DataFrame(columns=[
            "distribution_id", "request_id", "donation_id", "recipient_id",
            "recipient_name", "collected_at", "distributed_at",
            "people_served", "distribution_location", "notes", "status"
        ])

    df = df.copy()
    df["people_served"] = pd.to_numeric(df["people_served"], errors="coerce").fillna(0).astype(int)
    df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce")
    df["distributed_at"] = pd.to_datetime(df["distributed_at"], errors="coerce")
    
    for col in ["status", "recipient_name", "distribution_location"]:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.title().replace({"": "Unknown", "Nan": "Unknown"})
            
    if "distribution_id" in df.columns:
        df = df.drop_duplicates(subset=["distribution_id"])
    else:
        df = df.drop_duplicates()
        
    return df.reset_index(drop=True)


def load_clean_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load and clean all three primary operational CSV datasets using utils.storage.
    Returns: (cleaned_donations, cleaned_requests, cleaned_distributions)
    """
    donations_raw = storage.load("donations")
    requests_raw = storage.load("requests")
    dists_raw = storage.load("distributions")
    
    return (
        clean_donations(donations_raw),
        clean_requests(requests_raw),
        clean_distributions(dists_raw)
    )


# ==============================================================================
# 2. KEY PERFORMANCE INDICATOR (KPI) ENGINE
# ==============================================================================

def compute_kpis(donations: pd.DataFrame, requests: pd.DataFrame, dists: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate comprehensive, unit-accurate KPIs for live operational data.
    
    Definitions & Formulas:
    - Total Food Listed (kg): Sum of all valid donation quantities recorded.
    - Food Rescued & Distributed (kg): Sum of quantities where status is 'Distributed'.
    - Food Expired / Wasted (kg): Sum of quantities where status is 'Expired'.
    - Food In Pipeline (kg): Total Listed - (Distributed + Expired).
    - Meals Delivered: Total individual servings recorded for distributed donations.
    - People Served: Total verified beneficiaries recorded in distributions.csv.
    - Rescue Rate (%): (Food Rescued kg / Total Food Listed kg) * 100.
    - Wastage Rate (%): (Food Expired kg / Total Food Listed kg) * 100.
    - Request Approval Rate (%): (Approved Requests / Total Decided Requests) * 100.
    - Average NGO Response Time (hours): Mean elapsed time between requested_at and decided_at.
    - Active Donors & NGOs: Distinct participant counts.
    """
    total_listed_kg = float(donations["quantity_kg"].sum()) if not donations.empty else 0.0
    
    rescued_df = donations[donations["status"] == "Distributed"] if not donations.empty else pd.DataFrame()
    expired_df = donations[donations["status"] == "Expired"] if not donations.empty else pd.DataFrame()
    
    rescued_kg = float(rescued_df["quantity_kg"].sum()) if not rescued_df.empty else 0.0
    expired_kg = float(expired_df["quantity_kg"].sum()) if not expired_df.empty else 0.0
    pipeline_kg = max(0.0, total_listed_kg - (rescued_kg + expired_kg))
    
    meals_delivered = int(rescued_df["servings"].sum()) if not rescued_df.empty else 0
    people_served = int(dists["people_served"].sum()) if not dists.empty else 0
    
    # Safe division percentage helper
    def safe_pct(numerator: float, denominator: float) -> float:
        if denominator <= 0 or np.isnan(denominator) or np.isnan(numerator):
            return 0.0
        return round(float(100.0 * numerator / denominator), 1)

    rescue_rate = safe_pct(rescued_kg, total_listed_kg)
    wastage_rate = safe_pct(expired_kg, total_listed_kg)
    
    # Request metrics
    if not requests.empty:
        decided = requests[requests["status"].isin(COMPLETED_STATUSES + ["Rejected"])]
        approved = requests[requests["status"].isin(COMPLETED_STATUSES)]
        approval_rate = safe_pct(len(approved), len(decided))
        
        # Turnaround duration
        valid_times = requests.dropna(subset=["requested_at", "decided_at"]).copy()
        if not valid_times.empty:
            diff_hours = (valid_times["decided_at"] - valid_times["requested_at"]).dt.total_seconds() / 3600.0
            # Remove negative durations (clock skew)
            diff_hours = diff_hours[diff_hours >= 0]
            avg_response_hours = round(float(diff_hours.mean()), 1) if not diff_hours.empty else 0.0
        else:
            avg_response_hours = 0.0
    else:
        approval_rate = 0.0
        avg_response_hours = 0.0

    active_donors = int(donations["donor_id"].nunique()) if ("donor_id" in donations.columns and not donations.empty) else 0
    active_ngos = int(dists["recipient_id"].nunique()) if ("recipient_id" in dists.columns and not dists.empty) else 0

    return {
        "Total donations": int(len(donations)),
        "Total food listed (kg)": round(total_listed_kg, 1),
        "Food rescued & distributed (kg)": round(rescued_kg, 1),
        "Food expired / wasted (kg)": round(expired_kg, 1),
        "Food in redistribution pipeline (kg)": round(pipeline_kg, 1),
        "Meals delivered": meals_delivered,
        "People served": people_served,
        "Rescue rate (%)": rescue_rate,
        "Wastage rate (%)": wastage_rate,
        "Request approval rate (%)": approval_rate,
        "Avg. response time (hours)": avg_response_hours,
        "Active donors": active_donors,
        "Active NGOs": active_ngos,
    }


# ==============================================================================
# 3. LIVE AGGREGATIONS & VISUALIZATION SUMMARIES
# ==============================================================================

def monthly_trend(donations: pd.DataFrame) -> pd.DataFrame:
    """Monthly aggregation of food weight (kg) and donation count."""
    if donations.empty or "month" not in donations.columns:
        return pd.DataFrame(columns=["month", "donations", "food_kg"])
    return (
        donations.groupby("month", as_index=False)
        .agg(donations=("donation_id", "count"), food_kg=("quantity_kg", "sum"))
        .sort_values("month")
        .reset_index(drop=True)
    )


def daily_trend(donations: pd.DataFrame) -> pd.DataFrame:
    """Daily aggregation of food weight (kg)."""
    if donations.empty or "date" not in donations.columns:
        return pd.DataFrame(columns=["date", "quantity_kg"])
    return (
        donations.groupby("date", as_index=False)["quantity_kg"]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )


def by_category(donations: pd.DataFrame) -> pd.DataFrame:
    """Category breakdown of donations and total kilogram weight."""
    if donations.empty or "category" not in donations.columns:
        return pd.DataFrame(columns=["category", "donations", "food_kg", "percentage"])
    res = (
        donations.groupby("category", as_index=False)
        .agg(donations=("donation_id", "count"), food_kg=("quantity_kg", "sum"))
        .sort_values("food_kg", ascending=False)
        .reset_index(drop=True)
    )
    total_kg = res["food_kg"].sum()
    res["percentage"] = (res["food_kg"] / total_kg * 100).round(1) if total_kg > 0 else 0.0
    return res


def by_city(donations: pd.DataFrame) -> pd.DataFrame:
    """Geographic breakdown comparing listed food kg vs rescued food kg by city."""
    if donations.empty or "city" not in donations.columns:
        return pd.DataFrame(columns=["city", "donations", "food_kg", "rescued_kg", "rescue_rate_pct"])
    
    total_by_city = (
        donations.groupby("city", as_index=False)
        .agg(donations=("donation_id", "count"), food_kg=("quantity_kg", "sum"))
    )
    
    rescued_mask = donations["status"] == "Distributed"
    rescued_by_city = (
        donations[rescued_mask]
        .groupby("city")["quantity_kg"]
        .sum()
        .rename("rescued_kg")
    )
    
    out = total_by_city.merge(rescued_by_city, on="city", how="left").fillna({"rescued_kg": 0.0})
    out["rescue_rate_pct"] = (out["rescued_kg"] / out["food_kg"] * 100).round(1)
    return out.sort_values("food_kg", ascending=False).reset_index(drop=True)


def by_status(donations: pd.DataFrame) -> pd.DataFrame:
    """Distribution of food donations across operational statuses."""
    if donations.empty or "status" not in donations.columns:
        return pd.DataFrame(columns=["status", "donations", "percentage"])
    counts = donations["status"].value_counts().reset_index()
    counts.columns = ["status", "donations"]
    total = counts["donations"].sum()
    counts["percentage"] = (counts["donations"] / total * 100).round(1) if total > 0 else 0.0
    return counts


def top_donors(donations: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Top N food contributors ranked by total kilogram weight."""
    if donations.empty or "donor_name" not in donations.columns:
        return pd.DataFrame(columns=["donor_name", "donations", "food_kg"])
    return (
        donations.groupby("donor_name", as_index=False)
        .agg(donations=("donation_id", "count"), food_kg=("quantity_kg", "sum"))
        .sort_values("food_kg", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def top_ngos(dists: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Top N recipient NGO organizations ranked by total beneficiaries served."""
    if dists.empty or "recipient_name" not in dists.columns:
        return pd.DataFrame(columns=["recipient_name", "distributions", "people_served"])
    completed = dists[dists["status"] == "Distributed"]
    if completed.empty:
        return pd.DataFrame(columns=["recipient_name", "distributions", "people_served"])
    return (
        completed.groupby("recipient_name", as_index=False)
        .agg(distributions=("distribution_id", "count"), people_served=("people_served", "sum"))
        .sort_values("people_served", ascending=False)
        .head(n)
        .reset_index(drop=True)
    )


def category_city_pivot(donations: pd.DataFrame) -> pd.DataFrame:
    """Cross-tabulated pivot matrix of Food Category x City (kg)."""
    if donations.empty or "city" not in donations.columns or "category" not in donations.columns:
        return pd.DataFrame()
    return donations.pivot_table(
        index="city",
        columns="category",
        values="quantity_kg",
        aggfunc="sum",
        fill_value=0.0
    )


# ==============================================================================
# 4. KAGGLE / EXTERNAL FOOD WASTE DATASET ENGINE
# ==============================================================================

# Flexible column detection candidate lists for heterogeneous Kaggle datasets
CANDIDATE_DATE_COLS = ["date", "datetime", "timestamp", "waste_date", "day", "record_date"]
CANDIDATE_FOOD_COLS = ["food_category", "dish_category", "food_type", "category", "meal_type", "item", "food_item"]
CANDIDATE_WASTE_COLS = ["food_wasted_kg", "wastage_kg", "food_waste_kg", "waste_kg", "waste_quantity", "quantity_wasted", "wastage", "waste"]
CANDIDATE_PREPARED_COLS = ["food_prepared_kg", "quantity_prepared", "prepared_kg", "total_prepared", "quantity_cooked"]
CANDIDATE_LOC_COLS = ["location", "city", "canteen", "restaurant", "center", "campus", "establishment"]


def detect_column(columns: List[str], candidate_keywords: List[str]) -> Optional[str]:
    """
    Match dataframe columns against keyword candidates using exact and substring heuristics.
    """
    col_map = {c.strip().lower().replace(" ", "_"): c for c in columns}
    # 1. Exact match
    for cand in candidate_keywords:
        if cand in col_map:
            return col_map[cand]
    # 2. Substring match
    for cand in candidate_keywords:
        for clean_col, orig in col_map.items():
            if cand in clean_col:
                return orig
    return None


def auto_detect_dataset_schema(df: pd.DataFrame) -> Dict[str, Optional[str]]:
    """
    Automatically detect Date, Category, Waste Quantity, Prepared Quantity, and Location columns.
    """
    cols = list(df.columns)
    return {
        "date_col": detect_column(cols, CANDIDATE_DATE_COLS),
        "category_col": detect_column(cols, CANDIDATE_FOOD_COLS),
        "waste_col": detect_column(cols, CANDIDATE_WASTE_COLS),
        "prepared_col": detect_column(cols, CANDIDATE_PREPARED_COLS),
        "location_col": detect_column(cols, CANDIDATE_LOC_COLS),
    }


def clean_waste_dataset(
    df: pd.DataFrame,
    date_col: Optional[str] = None,
    waste_col: Optional[str] = None,
    category_col: Optional[str] = None,
    location_col: Optional[str] = None
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean, validate, and summarize any uploaded or Kaggle historical food waste dataset.
    
    Features:
    - Normalizes column names (strips whitespace, replaces non-alphanumeric with underscores).
    - Removes identical duplicate rows.
    - Safely parses dates into datetime format.
    - Strips non-numeric characters from numeric columns ('kg', ',', etc.).
    - Filters out negative numbers (physically impossible waste amounts).
    - Imputes missing numeric values with column median and records count.
    - Fills missing category values with 'Unknown'.
    - Produces a comprehensive Data Quality Audit Report.
    """
    if df.empty:
        return df, {
            "rows_before": 0, "rows_after": 0, "duplicates_removed": 0,
            "missing_imputed": 0, "negative_dropped": 0, "columns": []
        }

    raw_count = len(df)
    df_clean = df.copy()
    
    # 1. Normalize headers
    df_clean.columns = [re.sub(r"[^\w\s]", "_", str(c)).strip().replace(" ", "_") for c in df_clean.columns]
    
    # Map normalized column references if passed
    def norm_name(c: Optional[str]) -> Optional[str]:
        if not c:
            return None
        return re.sub(r"[^\w\s]", "_", str(c)).strip().replace(" ", "_")

    date_col_norm = norm_name(date_col)
    waste_col_norm = norm_name(waste_col)
    category_col_norm = norm_name(category_col)
    location_col_norm = norm_name(location_col)

    # 2. Deduplication
    df_clean = df_clean.drop_duplicates()
    dupes_removed = raw_count - len(df_clean)
    
    # 3. Date conversion
    if date_col_norm and date_col_norm in df_clean.columns:
        df_clean[date_col_norm] = pd.to_datetime(df_clean[date_col_norm], errors="coerce")
    else:
        # Fallback date detection
        for c in df_clean.columns:
            if "date" in c.lower() or "day" in c.lower() or "time" in c.lower():
                converted = pd.to_datetime(df_clean[c], errors="coerce")
                if converted.notna().mean() > 0.5:
                    df_clean[c] = converted
                    date_col_norm = c
                    break

    # 4. Clean text representations in numeric columns
    for c in df_clean.select_dtypes(include=["object", "string"]).columns:
        if c == date_col_norm:
            continue
        # Check if text is actually numbers with 'kg' or commas
        sample = df_clean[c].dropna().astype(str)
        cleaned_sample = sample.str.replace("kg", "", case=False).str.replace(",", "").str.strip()
        converted = pd.to_numeric(cleaned_sample, errors="coerce")
        if converted.notna().mean() > 0.70:
            df_clean[c] = converted

    # 5. Clean Waste Column specifically
    negative_rows_removed = 0
    if waste_col_norm and waste_col_norm in df_clean.columns:
        df_clean[waste_col_norm] = pd.to_numeric(df_clean[waste_col_norm], errors="coerce")
        before_neg = len(df_clean)
        # Drop negative waste rows
        df_clean = df_clean[df_clean[waste_col_norm].isna() | (df_clean[waste_col_norm] >= 0)]
        negative_rows_removed = before_neg - len(df_clean)

    # 6. Track and impute missing values
    missing_count = int(df_clean.isna().sum().sum())
    numeric_cols = df_clean.select_dtypes(include=[np.number]).columns
    for num_col in numeric_cols:
        median_val = df_clean[num_col].median()
        if pd.isna(median_val):
            median_val = 0.0
        df_clean[num_col] = df_clean[num_col].fillna(round(median_val, 2))

    # Text columns fill with 'Unknown'
    text_cols = [c for c in df_clean.columns if c not in numeric_cols and not pd.api.types.is_datetime64_any_dtype(df_clean[c])]
    for txt_col in text_cols:
        df_clean[txt_col] = df_clean[txt_col].fillna("Unknown").astype(str).str.strip().str.title()

    report = {
        "rows_before": raw_count,
        "rows_after": len(df_clean),
        "duplicates_removed": dupes_removed,
        "missing_imputed": missing_count,
        "negative_dropped": negative_rows_removed,
        "date_col": date_col_norm,
        "waste_col": waste_col_norm,
        "category_col": category_col_norm,
        "location_col": location_col_norm,
        "columns": list(df_clean.columns)
    }

    return df_clean.reset_index(drop=True), report


def compute_waste_metrics(df: pd.DataFrame, waste_col: str) -> Dict[str, Any]:
    """
    Compute statistical food waste metrics for a verified waste column.
    """
    if df.empty or waste_col not in df.columns:
        return {
            "total_waste_kg": 0.0, "avg_waste_kg": 0.0, "median_waste_kg": 0.0,
            "max_waste_kg": 0.0, "min_waste_kg": 0.0, "std_waste_kg": 0.0, "record_count": 0
        }
    
    series = pd.to_numeric(df[waste_col], errors="coerce").dropna()
    if series.empty:
        return {
            "total_waste_kg": 0.0, "avg_waste_kg": 0.0, "median_waste_kg": 0.0,
            "max_waste_kg": 0.0, "min_waste_kg": 0.0, "std_waste_kg": 0.0, "record_count": 0
        }
        
    return {
        "total_waste_kg": round(float(series.sum()), 2),
        "avg_waste_kg": round(float(series.mean()), 2),
        "median_waste_kg": round(float(series.median()), 2),
        "max_waste_kg": round(float(series.max()), 2),
        "min_waste_kg": round(float(series.min()), 2),
        "std_waste_kg": round(float(series.std()), 2) if len(series) > 1 else 0.0,
        "record_count": int(len(series))
    }
