"""Shared constants used across the whole project."""

APP_NAME = "Smart Food Rescue"
APP_TAGLINE = "Food Waste Reduction & Donation Analytics Platform  |  SDG 2 - Zero Hunger"

ROLE_DONOR = "Donor"
ROLE_RECIPIENT = "Recipient/NGO"
ROLE_ADMIN = "Admin"

CATEGORIES = [
    "Cooked Meals",
    "Bakery",
    "Fruits & Vegetables",
    "Dairy",
    "Packaged Food",
    "Grains & Pulses",
    "Beverages",
    "Other",
]

# Donation life-cycle:  Available -> Reserved -> Collected -> Distributed
#                       (or Expired if nobody collects it in time)
DONATION_STATUSES = ["Available", "Reserved", "Collected", "Distributed", "Expired"]

# Request life-cycle:   Pending -> Approved -> Collected -> Distributed
#                       (or Rejected / Cancelled)
REQUEST_STATUSES = ["Pending", "Approved", "Rejected", "Collected", "Distributed", "Cancelled"]

DATE_FMT = "%Y-%m-%d %H:%M"
