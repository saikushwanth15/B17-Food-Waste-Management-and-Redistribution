"""
================================================================================
UNIT TESTS: test_analytics.py
MEMBER 3 DELIVERABLE: L Sai Kushwanth
================================================================================
Comprehensive test suite testing data cleaning, KPI calculations, Kaggle dataset
handling, edge cases (zero division, missing values, negative quantities), and
in-memory ReportLab PDF generation.

Run with:
    python -m unittest tests/test_analytics.py -v
================================================================================
"""

import os
import sys
import unittest
import pandas as pd
import numpy as np

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules import analysis, reports


class TestLiveOperationalCleaning(unittest.TestCase):
    """Tests for live operational data cleaning (donations, requests, distributions)."""

    def test_clean_donations_empty(self):
        """Empty donation dataframe should return expected columns without errors."""
        empty_df = pd.DataFrame()
        cleaned = analysis.clean_donations(empty_df)
        self.assertTrue(cleaned.empty)
        self.assertIn("quantity_kg", cleaned.columns)
        self.assertIn("month", cleaned.columns)

    def test_clean_donations_duplicates_and_types(self):
        """Duplicate donation_ids and string numbers should be cleaned."""
        raw = pd.DataFrame([
            {"donation_id": "D001", "quantity_kg": "25.5", "servings": "10", "category": "cooked meals", "city": "hyderabad", "status": "available", "created_at": "2026-10-10 10:00"},
            {"donation_id": "D001", "quantity_kg": "25.5", "servings": "10", "category": "cooked meals", "city": "hyderabad", "status": "available", "created_at": "2026-10-10 10:00"}, # Duplicate
            {"donation_id": "D002", "quantity_kg": "-15", "servings": "0", "category": "bakery", "city": "hyderabad", "status": "available", "created_at": "2026-10-10 11:00"}, # Negative
            {"donation_id": "D003", "quantity_kg": "0", "servings": "0", "category": "bakery", "city": "hyderabad", "status": "available", "created_at": "2026-10-10 11:00"}, # Zero
            {"donation_id": "D004", "quantity_kg": "invalid", "servings": "0", "category": "bakery", "city": "hyderabad", "status": "available", "created_at": "2026-10-10 11:00"}, # Invalid numeric
            {"donation_id": "D005", "quantity_kg": "40.0", "servings": "50", "category": "raw ingredients", "city": "bengaluru", "status": "distributed", "created_at": "2026-10-11 12:00"},
        ])
        cleaned = analysis.clean_donations(raw)
        self.assertEqual(len(cleaned), 2)  # Only D001 and D005 survive
        self.assertListEqual(list(cleaned["donation_id"]), ["D001", "D005"])
        self.assertEqual(cleaned.iloc[0]["category"], "Cooked Meals")
        self.assertEqual(cleaned.iloc[0]["city"], "Hyderabad")
        self.assertEqual(cleaned.iloc[0]["month"], "2026-10")

    def test_clean_requests_and_distributions(self):
        """Check date parsing, type coercion, and deduplication for requests and distributions."""
        raw_req = pd.DataFrame([
            {"request_id": "R001", "status": "pending", "requested_at": "2026-10-10 10:00", "decided_at": ""},
            {"request_id": "R001", "status": "pending", "requested_at": "2026-10-10 10:00", "decided_at": ""},
        ])
        clean_req = analysis.clean_requests(raw_req)
        self.assertEqual(len(clean_req), 1)

        raw_dist = pd.DataFrame([
            {"distribution_id": "T001", "people_served": "150", "collected_at": "2026-10-10 11:00", "distributed_at": "2026-10-10 13:00", "status": "distributed"},
            {"distribution_id": "T001", "people_served": "150", "collected_at": "2026-10-10 11:00", "distributed_at": "2026-10-10 13:00", "status": "distributed"},
            {"distribution_id": "T002", "people_served": "invalid", "collected_at": "2026-10-10 11:00", "distributed_at": "2026-10-10 13:00", "status": "distributed"},
        ])
        clean_dist = analysis.clean_distributions(raw_dist)
        self.assertEqual(len(clean_dist), 2)
        self.assertEqual(clean_dist.iloc[0]["people_served"], 150)
        self.assertEqual(clean_dist.iloc[1]["people_served"], 0)


class TestKPIEngine(unittest.TestCase):
    """Tests for KPI engine and division-by-zero safety."""

    def test_kpi_empty_state_zero_division(self):
        """When dataframes are completely empty, KPIs must return 0.0 without ZeroDivisionError."""
        empty_donations = pd.DataFrame(columns=["quantity_kg", "status", "servings", "donor_id"])
        empty_requests = pd.DataFrame(columns=["status", "requested_at", "decided_at", "recipient_id"])
        empty_dists = pd.DataFrame(columns=["people_served", "recipient_id", "status"])

        kpis = analysis.compute_kpis(empty_donations, empty_requests, empty_dists)
        self.assertEqual(kpis["Total donations"], 0)
        self.assertEqual(kpis["Total food listed (kg)"], 0.0)
        self.assertEqual(kpis["Food rescued & distributed (kg)"], 0.0)
        self.assertEqual(kpis["Rescue rate (%)"], 0.0)
        self.assertEqual(kpis["Wastage rate (%)"], 0.0)
        self.assertEqual(kpis["Request approval rate (%)"], 0.0)
        self.assertEqual(kpis["Avg. response time (hours)"], 0.0)

    def test_kpi_calculations_accurate(self):
        """Check KPI calculation accuracy on realistic multi-status data."""
        donations = pd.DataFrame([
            {"donation_id": "D1", "quantity_kg": 100.0, "status": "Distributed", "servings": 200, "donor_id": "U1"},
            {"donation_id": "D2", "quantity_kg": 50.0, "status": "Distributed", "servings": 100, "donor_id": "U1"},
            {"donation_id": "D3", "quantity_kg": 30.0, "status": "Expired", "servings": 60, "donor_id": "U2"},
            {"donation_id": "D4", "quantity_kg": 20.0, "status": "Available", "servings": 40, "donor_id": "U2"},
        ])
        requests = pd.DataFrame([
            {"request_id": "R1", "status": "Distributed", "requested_at": pd.Timestamp("2026-10-10 10:00"), "decided_at": pd.Timestamp("2026-10-10 12:00")}, # 2 hrs
            {"request_id": "R2", "status": "Rejected", "requested_at": pd.Timestamp("2026-10-10 10:00"), "decided_at": pd.Timestamp("2026-10-10 14:00")},    # 4 hrs
        ])
        dists = pd.DataFrame([
            {"distribution_id": "T1", "people_served": 250, "recipient_id": "U3", "status": "Distributed"},
        ])

        kpis = analysis.compute_kpis(donations, requests, dists)
        self.assertEqual(kpis["Total donations"], 4)
        self.assertEqual(kpis["Total food listed (kg)"], 200.0)
        self.assertEqual(kpis["Food rescued & distributed (kg)"], 150.0)
        self.assertEqual(kpis["Food expired / wasted (kg)"], 30.0)
        self.assertEqual(kpis["Food in redistribution pipeline (kg)"], 20.0)
        self.assertEqual(kpis["Rescue rate (%)"], 75.0)   # 150 / 200 * 100
        self.assertEqual(kpis["Wastage rate (%)"], 15.0)  # 30 / 200 * 100
        self.assertEqual(kpis["Meals delivered"], 300)
        self.assertEqual(kpis["People served"], 250)
        self.assertEqual(kpis["Request approval rate (%)"], 50.0) # 1 of 2 approved
        self.assertEqual(kpis["Avg. response time (hours)"], 3.0) # (2+4)/2


class TestKaggleDatasetHandling(unittest.TestCase):
    """Tests for auto-detection and cleaning of university canteen and restaurant waste CSVs."""

    def test_auto_detect_canteen_schema(self):
        """Auto detection on canteen dataset schema."""
        canteen_df = pd.DataFrame(columns=[
            "Date", "Meal_Type", "Day_Of_Week", "Students_Present", "Food_Prepared_kg", "Food_Wasted_kg", "Food_Category"
        ])
        schema = analysis.auto_detect_dataset_schema(canteen_df)
        self.assertEqual(schema["date_col"], "Date")
        self.assertEqual(schema["waste_col"], "Food_Wasted_kg")
        self.assertEqual(schema["category_col"], "Food_Category")

    def test_auto_detect_restaurant_schema(self):
        """Auto detection on restaurant dataset schema."""
        restaurant_df = pd.DataFrame(columns=[
            "Date", "Dish_Category", "Quantity_Prepared", "Quantity_Sold", "Wastage_kg", "Wastage_Reason", "Unit_Price"
        ])
        schema = analysis.auto_detect_dataset_schema(restaurant_df)
        self.assertEqual(schema["date_col"], "Date")
        self.assertEqual(schema["waste_col"], "Wastage_kg")
        self.assertEqual(schema["category_col"], "Dish_Category")

    def test_clean_waste_dataset_drops_negatives_and_dupes(self):
        """Generic waste cleaner must drop duplicate rows and negative waste amounts."""
        raw = pd.DataFrame([
            {"Date": "2026-05-01", "Dish_Category": "Dessert", "Wastage_kg": "5.5"},
            {"Date": "2026-05-01", "Dish_Category": "Dessert", "Wastage_kg": "5.5"},  # Duplicate
            {"Date": "2026-05-02", "Dish_Category": "Main Course", "Wastage_kg": "-3.2"},  # Negative
            {"Date": "2026-05-03", "Dish_Category": "Bakery", "Wastage_kg": "12.0 kg"},    # Text with 'kg'
            {"Date": "2026-05-04", "Dish_Category": None, "Wastage_kg": None},             # Missing
        ])
        clean_df, report = analysis.clean_waste_dataset(raw, waste_col="Wastage_kg", category_col="Dish_Category", date_col="Date")
        
        self.assertEqual(report["rows_before"], 5)
        self.assertEqual(report["duplicates_removed"], 1)
        self.assertEqual(report["negative_dropped"], 1)
        self.assertEqual(report["rows_after"], 3)
        self.assertEqual(clean_df.iloc[1]["Wastage_kg"], 12.0)
        self.assertEqual(clean_df.iloc[2]["Dish_Category"], "Unknown")


class TestPDFReportGeneration(unittest.TestCase):
    """Tests in-memory PDF synthesis using ReportLab."""

    def setUp(self):
        self.sample_kpis = {
            "Total donations": 10,
            "Total food listed (kg)": 250.0,
            "Food rescued & distributed (kg)": 180.0,
            "Food expired / wasted (kg)": 40.0,
            "Food in redistribution pipeline (kg)": 30.0,
            "Meals delivered": 750,
            "People served": 600,
            "Rescue rate (%)": 72.0,
            "Wastage rate (%)": 16.0,
            "Request approval rate (%)": 90.0,
            "Avg. response time (hours)": 2.5,
            "Active donors": 3,
            "Active NGOs": 2,
        }
        self.monthly = pd.DataFrame({"month": ["2026-09", "2026-10"], "donations": [4, 6], "food_kg": [100.0, 150.0]})
        self.cats = pd.DataFrame({"category": ["Cooked Meals", "Bakery"], "donations": [6, 4], "food_kg": [180.0, 70.0], "percentage": [72.0, 28.0]})
        self.cities = pd.DataFrame({"city": ["Hyderabad"], "donations": [10], "food_kg": [250.0], "rescued_kg": [180.0], "rescue_rate_pct": [72.0]})
        self.statuses = pd.DataFrame({"status": ["Distributed", "Expired"], "donations": [7, 3], "percentage": [70.0, 30.0]})
        self.donors = pd.DataFrame({"donor_name": ["Paradise Canteen"], "donations": [10], "food_kg": [250.0]})
        self.ngos = pd.DataFrame({"recipient_name": ["Robin Hood Army"], "distributions": [5], "people_served": [600]})

    def test_build_analytics_report_bytes(self):
        """build_analytics_report should return non-empty valid PDF bytes."""
        pdf_bytes = reports.build_analytics_report(
            self.sample_kpis, self.monthly, self.cats, self.cities, self.statuses, self.donors, self.ngos
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_build_evaluation_summary_bytes(self):
        """build_evaluation_summary should return non-empty valid PDF bytes."""
        pdf_bytes = reports.build_evaluation_summary(self.sample_kpis)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_build_waste_dataset_report_bytes(self):
        """build_waste_dataset_report should return valid PDF bytes."""
        cleaning_report = {
            "rows_before": 100, "rows_after": 95, "duplicates_removed": 2,
            "negative_dropped": 3, "missing_imputed": 5, "waste_col": "Food_Wasted_kg"
        }
        waste_metrics = {
            "total_waste_kg": 540.2, "avg_waste_kg": 5.68, "median_waste_kg": 5.1,
            "max_waste_kg": 18.5, "min_waste_kg": 0.5, "std_waste_kg": 2.8, "record_count": 95
        }
        pdf_bytes = reports.build_waste_dataset_report(
            "Canteen_Waste_Audit.csv", cleaning_report, waste_metrics
        )
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
