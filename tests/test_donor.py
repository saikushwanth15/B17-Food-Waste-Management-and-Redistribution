"""
================================================================================
UNIT TESTS: test_donor.py
MEMBER 1 DELIVERABLE: N Thulasi Krishna
================================================================================
Comprehensive test suite testing food donation input validation, catalog filtering,
CRUD operations, and user registration/authentication security.

Run with:
    python -m unittest tests/test_donor.py -v
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

from modules import donor
from utils import auth, storage


class TestDonationValidation(unittest.TestCase):
    """Tests for Member 1 food donation form validation logic."""

    def test_valid_donation(self):
        """A properly formatted donation should return no validation errors."""
        future_exp = datetime.now() + timedelta(hours=8)
        errors = donor.validate_donation(
            food_name="Vegetable Biryani",
            quantity=15.0,
            servings=30,
            city="Hyderabad",
            address="Plot 42, Hitech City Main Road",
            expiry=future_exp,
            category="Cooked Meals"
        )
        self.assertEqual(errors, [])

    def test_short_food_name(self):
        """Food name with fewer than 3 characters must fail validation."""
        future_exp = datetime.now() + timedelta(hours=4)
        errors = donor.validate_donation(
            food_name="AB",
            quantity=5.0,
            servings=10,
            city="Hyderabad",
            address="Plot 42, Hitech City Main Road",
            expiry=future_exp
        )
        self.assertTrue(any("at least 3 characters" in e for e in errors))

    def test_zero_or_negative_quantity(self):
        """Zero or negative quantity values must be rejected."""
        future_exp = datetime.now() + timedelta(hours=4)
        errors_zero = donor.validate_donation("Rice & Curry", 0.0, 10, "Hyderabad", "Valid address", future_exp)
        errors_neg = donor.validate_donation("Rice & Curry", -5.0, 10, "Hyderabad", "Valid address", future_exp)
        self.assertTrue(any("greater than 0 kg" in e for e in errors_zero))
        self.assertTrue(any("greater than 0 kg" in e for e in errors_neg))

    def test_zero_servings(self):
        """Zero servings must be rejected."""
        future_exp = datetime.now() + timedelta(hours=4)
        errors = donor.validate_donation("Fresh Bread", 5.0, 0, "Hyderabad", "Valid address", future_exp)
        self.assertTrue(any("at least 1 portion" in e for e in errors))

    def test_past_expiry_datetime(self):
        """An expiration date/time in the past must be rejected."""
        past_exp = datetime.now() - timedelta(minutes=30)
        errors = donor.validate_donation("Fresh Apples", 10.0, 20, "Hyderabad", "Valid address", past_exp)
        self.assertTrue(any("must be in the future" in e for e in errors))

    def test_missing_location(self):
        """Blank city or short address must fail."""
        future_exp = datetime.now() + timedelta(hours=5)
        errors_city = donor.validate_donation("Bread", 5.0, 10, "", "Valid Address 123", future_exp)
        errors_addr = donor.validate_donation("Bread", 5.0, 10, "Hyderabad", "No", future_exp)
        self.assertTrue(any("City / Region is required" in e for e in errors_city))
        self.assertTrue(any("pickup address" in e for e in errors_addr))


class TestDonationFilteringAndSorting(unittest.TestCase):
    """Tests for donation search, multi-attribute filtering, and sorting."""

    def setUp(self):
        self.df = pd.DataFrame([
            {"donation_id": "D001", "donor_name": "Paradise Canteen", "food_name": "Vegetable Biryani", "category": "Cooked Meals", "quantity_kg": "25.0", "city": "Hyderabad", "status": "Available", "created_at": "2026-10-15 10:00", "expiry_datetime": "2026-10-15 18:00", "notes": "Mild spice"},
            {"donation_id": "D002", "donor_name": "Karachi Bakery", "food_name": "Fruit Biscuits", "category": "Bakery", "quantity_kg": "10.0", "city": "Hyderabad", "status": "Available", "created_at": "2026-10-15 11:00", "expiry_datetime": "2026-10-20 18:00", "notes": "Eggless"},
            {"donation_id": "D003", "donor_name": "Green Veg Mart", "food_name": "Fresh Tomatoes", "category": "Fruits & Vegetables", "quantity_kg": "50.0", "city": "Bengaluru", "status": "Distributed", "created_at": "2026-10-14 09:00", "expiry_datetime": "2026-10-16 12:00", "notes": "Ripe"},
            {"donation_id": "D004", "donor_name": "Taj Catering", "food_name": "Paneer Butter Masala", "category": "Cooked Meals", "quantity_kg": "15.0", "city": "Chennai", "status": "Expired", "created_at": "2026-10-13 14:00", "expiry_datetime": "2026-10-13 22:00", "notes": "North Indian"},
        ])

    def test_search_by_keyword(self):
        """Search query should match food_name, donor_name, or notes."""
        res_food = donor.filter_donations_dataframe(self.df, search_text="biryani")
        self.assertEqual(len(res_food), 1)
        self.assertEqual(res_food.iloc[0]["donation_id"], "D001")

        res_note = donor.filter_donations_dataframe(self.df, search_text="eggless")
        self.assertEqual(len(res_note), 1)
        self.assertEqual(res_note.iloc[0]["donation_id"], "D002")

    def test_filter_by_category_and_status(self):
        """Filter by category and status simultaneously."""
        res_cat = donor.filter_donations_dataframe(self.df, categories=["Cooked Meals"])
        self.assertEqual(len(res_cat), 2)

        res_status = donor.filter_donations_dataframe(self.df, statuses=["Available"])
        self.assertEqual(len(res_status), 2)

        res_both = donor.filter_donations_dataframe(self.df, categories=["Cooked Meals"], statuses=["Available"])
        self.assertEqual(len(res_both), 1)
        self.assertEqual(res_both.iloc[0]["donation_id"], "D001")

    def test_sort_by_quantity(self):
        """Sorting by highest quantity should place D003 (50 kg) first."""
        sorted_df = donor.filter_donations_dataframe(self.df, sort_by="Quantity (Highest First)")
        self.assertEqual(sorted_df.iloc[0]["donation_id"], "D003")
        self.assertEqual(sorted_df.iloc[-1]["donation_id"], "D002")


class TestUserAuthenticationSecurity(unittest.TestCase):
    """Tests for password hashing, regex validation, and authentication."""

    def test_password_hashing_and_verification(self):
        """Salted SHA-256 passwords must hash securely and verify correctly."""
        raw_pw = "donorSecure123!"
        hashed = auth.hash_password(raw_pw)
        
        self.assertIn("$", hashed)
        self.assertNotEqual(hashed, raw_pw)
        self.assertTrue(auth.verify_password(raw_pw, hashed))
        self.assertFalse(auth.verify_password("wrongPassword", hashed))

    def test_email_validation_regex(self):
        """Regex should accept valid emails and reject invalid ones."""
        self.assertTrue(auth.is_valid_email("donor@example.com"))
        self.assertTrue(auth.is_valid_email("thulasi.krishna@college.edu"))
        self.assertFalse(auth.is_valid_email("invalid-email-address"))
        self.assertFalse(auth.is_valid_email("@domain.com"))
        self.assertFalse(auth.is_valid_email("user@.com"))

    def test_phone_validation_regex(self):
        """Indian mobile phone numbers must have 10 digits starting with 6, 7, 8, or 9."""
        self.assertTrue(auth.is_valid_phone("9876543210"))
        self.assertTrue(auth.is_valid_phone("8123456789"))
        self.assertFalse(auth.is_valid_phone("1234567890"))  # Starts with 1
        self.assertFalse(auth.is_valid_phone("98765"))       # Too short
        self.assertFalse(auth.is_valid_phone("98765432109")) # Too long


if __name__ == "__main__":
    unittest.main()
