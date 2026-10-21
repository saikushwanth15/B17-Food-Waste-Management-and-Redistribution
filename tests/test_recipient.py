"""
================================================================================
UNIT TESTS: test_recipient.py
MEMBER 2 DELIVERABLE: N Charya Vishwa
================================================================================
Comprehensive test suite testing recipient/NGO food catalog filtering,
request approval and conflict resolution, distribution tracking validation,
and automated expiration logic.

Run with:
    python -m unittest tests/test_recipient.py -v
================================================================================
"""

from datetime import datetime, timedelta
import os
import sys
import unittest
import pandas as pd

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from modules import recipient
from utils import storage


class TestDistributionValidation(unittest.TestCase):
    """Tests for Member 2 distribution logging validation."""

    def test_valid_distribution(self):
        """Valid headcount and location must return no errors."""
        errors = recipient.validate_distribution_entry(
            people_served=45,
            location="Sunrise Orphanage, Kukatpally"
        )
        self.assertEqual(errors, [])

    def test_zero_or_negative_beneficiaries(self):
        """Zero or negative headcount must be rejected."""
        errors_zero = recipient.validate_distribution_entry(0, "Slum Community Shelter")
        errors_neg = recipient.validate_distribution_entry(-10, "Slum Community Shelter")
        self.assertTrue(any("at least 1 person" in e for e in errors_zero))
        self.assertTrue(any("at least 1 person" in e for e in errors_neg))

    def test_short_or_blank_location(self):
        """Blank or too-short location descriptions must be rejected."""
        errors_blank = recipient.validate_distribution_entry(20, "")
        errors_short = recipient.validate_distribution_entry(20, "AB")
        self.assertTrue(any("at least 3 characters" in e for e in errors_blank))
        self.assertTrue(any("at least 3 characters" in e for e in errors_short))


class TestAvailableFoodCatalogFiltering(unittest.TestCase):
    """Tests for available surplus food catalog filtering and sorting."""

    def setUp(self):
        self.donations = pd.DataFrame([
            {"donation_id": "D101", "food_name": "Vegetable Biryani", "category": "Cooked Meals", "quantity_kg": "30.0", "city": "Hyderabad", "status": "Available", "expiry_datetime": "2026-10-25 14:00", "notes": "Freshly cooked"},
            {"donation_id": "D102", "food_name": "Sliced White Bread", "category": "Bakery", "quantity_kg": "15.0", "city": "Hyderabad", "status": "Available", "expiry_datetime": "2026-10-22 18:00", "notes": "Packaged loaves"},
            {"donation_id": "D103", "food_name": "Tomato Soup", "category": "Cooked Meals", "quantity_kg": "20.0", "city": "Bengaluru", "status": "Reserved", "expiry_datetime": "2026-10-22 12:00", "notes": "Reserved item"},
            {"donation_id": "D104", "food_name": "Paneer Pulao", "category": "Cooked Meals", "quantity_kg": "50.0", "city": "Chennai", "status": "Available", "expiry_datetime": "2026-10-23 20:00", "notes": "Large bulk quantity"},
        ])

    def test_only_available_status_shown(self):
        """Catalog should strictly exclude Reserved, Collected, or Expired items."""
        filtered = recipient.filter_available_food(self.donations)
        self.assertEqual(len(filtered), 3)  # D101, D102, D104
        self.assertNotIn("D103", list(filtered["donation_id"]))

    def test_keyword_search(self):
        """Search query matches food names and notes."""
        res = recipient.filter_available_food(self.donations, search_query="bread")
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["donation_id"], "D102")

    def test_city_and_category_filter(self):
        """Filter by city and food category."""
        res = recipient.filter_available_food(self.donations, categories=["Cooked Meals"], cities=["Hyderabad"])
        self.assertEqual(len(res), 1)
        self.assertEqual(res.iloc[0]["donation_id"], "D101")

    def test_sort_by_quantity_and_expiry(self):
        """Sorting by quantity descending puts largest food quantity first."""
        res_qty = recipient.filter_available_food(self.donations, sort_by="Quantity (Highest First)")
        self.assertEqual(res_qty.iloc[0]["donation_id"], "D104")  # 50 kg


class TestNGOMetricsCalculation(unittest.TestCase):
    """Tests for recipient dashboard metric aggregations."""

    def test_calculate_ngo_metrics(self):
        """Verify accurate calculation of an NGO's requests, collections, and people fed."""
        donations = pd.DataFrame([
            {"donation_id": "D1", "status": "Available", "quantity_kg": 25.0},
            {"donation_id": "D2", "status": "Available", "quantity_kg": 15.0},
            {"donation_id": "D3", "status": "Distributed", "quantity_kg": 40.0},
        ])
        requests = pd.DataFrame([
            {"request_id": "R1", "recipient_id": "NGO01", "status": "Pending"},
            {"request_id": "R2", "recipient_id": "NGO01", "status": "Approved"},
            {"request_id": "R3", "recipient_id": "NGO01", "status": "Collected"},
            {"request_id": "R4", "recipient_id": "OTHER", "status": "Pending"},
        ])
        dists = pd.DataFrame([
            {"distribution_id": "T1", "recipient_id": "NGO01", "status": "Distributed", "people_served": 120},
            {"distribution_id": "T2", "recipient_id": "NGO01", "status": "Distributed", "people_served": 80},
        ])

        metrics = recipient.calculate_ngo_metrics("NGO01", donations, requests, dists)
        self.assertEqual(metrics["available_listings"], 2)
        self.assertEqual(metrics["available_food_kg"], 40.0)
        self.assertEqual(metrics["my_pending_requests"], 1)
        self.assertEqual(metrics["my_approved_awaiting_pickup"], 1)
        self.assertEqual(metrics["my_collected_awaiting_dist"], 1)
        self.assertEqual(metrics["my_completed_distributions"], 2)
        self.assertEqual(metrics["total_people_served"], 200)


class TestApprovalAndConflictRejection(unittest.TestCase):
    """Tests approval logic and automatic competing request rejection."""

    def test_approve_request_logic(self):
        """Approving a request must reserve donation and reject competing requests."""
        # Setup temporary record in storage using generated IDs
        donation_id = storage.add_record("donations", {
            "donor_id": "U0001", "donor_name": "Test Donor", "food_name": "Test Food", "category": "Cooked Meals",
            "quantity_kg": "10.0", "servings": "20", "city": "Hyderabad", "pickup_address": "Test Addr",
            "expiry_datetime": "2026-12-31 23:59", "notes": "", "status": "Available", "created_at": storage.now_str()
        })
        req_winner = storage.add_record("requests", {
            "donation_id": donation_id, "recipient_id": "U1",
            "recipient_name": "NGO 1", "message": "", "status": "Pending", "requested_at": storage.now_str(), "decided_at": ""
        })
        req_loser = storage.add_record("requests", {
            "donation_id": donation_id, "recipient_id": "U2",
            "recipient_name": "NGO 2", "message": "", "status": "Pending", "requested_at": storage.now_str(), "decided_at": ""
        })

        try:
            recipient.approve_request(req_winner, donation_id)

            updated_donation = storage.get_record("donations", donation_id)
            updated_winner = storage.get_record("requests", req_winner)
            updated_loser = storage.get_record("requests", req_loser)

            self.assertIsNotNone(updated_donation)
            self.assertEqual(updated_donation["status"], "Reserved")
            self.assertEqual(updated_winner["status"], "Approved")
            self.assertEqual(updated_loser["status"], "Rejected")
        finally:
            # Clean up test rows
            storage.delete_record("donations", donation_id)
            storage.delete_record("requests", req_winner)
            storage.delete_record("requests", req_loser)


if __name__ == "__main__":
    unittest.main()
