"""
Fills the app with DEMO data so the dashboard looks good during the viva.
Run once:   python seed_data.py
(Run again with --reset to wipe everything and start over.)

Also writes two sample food-waste CSVs to data/waste_datasets/.  They are
small synthetic stand-ins with the same kind of columns as the Kaggle datasets
in the project brief; replace/add the real Kaggle files in that folder.
"""
import os
import random
import sys
from datetime import datetime, timedelta

import pandas as pd

from utils import auth, storage
from utils.constants import DATE_FMT

random.seed(7)
FMT = DATE_FMT


def seed_waste_datasets():
    folder = os.path.join(storage.DATA_DIR, "waste_datasets")
    os.makedirs(folder, exist_ok=True)

    # --- university canteen style dataset
    rows = []
    for i in range(120):
        day = datetime(2026, 1, 5) + timedelta(days=i)
        for meal in ["Breakfast", "Lunch", "Dinner"]:
            prepared = round(random.uniform(40, 120), 1)
            wasted = round(prepared * random.uniform(0.05, 0.30), 1)
            rows.append({"Date": day.date(), "Meal_Type": meal,
                         "Day_Of_Week": day.strftime("%A"),
                         "Students_Present": random.randint(250, 900),
                         "Food_Prepared_kg": prepared,
                         "Food_Wasted_kg": wasted,
                         "Food_Category": random.choice(["Rice", "Curry", "Bread", "Vegetables", "Dessert"])})
    pd.DataFrame(rows).to_csv(os.path.join(folder, "canteen_waste_sample.csv"), index=False)

    # --- restaurant style dataset
    rows = []
    for i in range(300):
        day = datetime(2026, 2, 1) + timedelta(days=random.randint(0, 150))
        prepared = random.randint(20, 150)
        sold = int(prepared * random.uniform(0.6, 0.98))
        rows.append({"Date": day.date(),
                     "Dish_Category": random.choice(["Starter", "Main Course", "Dessert", "Beverage", "Bakery"]),
                     "Quantity_Prepared": prepared, "Quantity_Sold": sold,
                     "Wastage_kg": round((prepared - sold) * random.uniform(0.2, 0.5), 2),
                     "Wastage_Reason": random.choice(["Overproduction", "Spoilage", "Customer leftover", "Preparation error"]),
                     "Unit_Price": random.choice([60, 90, 120, 150, 200])})
    df = pd.DataFrame(rows)
    df.loc[df.sample(8, random_state=1).index, "Wastage_Reason"] = None   # missing values to clean
    df = pd.concat([df, df.head(5)])                                       # duplicates to clean
    df.to_csv(os.path.join(folder, "restaurant_wastage_sample.csv"), index=False)


def seed_app_data():
    users = [  # name, email, role, org, city
        ("Spice Garden Restaurant", "spice@demo.com", "Donor", "Spice Garden", "Hyderabad"),
        ("Green Leaf Hostel", "hostel@demo.com", "Donor", "Green Leaf Hostel", "Hyderabad"),
        ("FreshMart Supermarket", "freshmart@demo.com", "Donor", "FreshMart", "Bengaluru"),
        ("Grand Hotel Kitchen", "grand@demo.com", "Donor", "Grand Hotel", "Chennai"),
        ("Hope Foundation", "hope@demo.com", "Recipient/NGO", "Hope Foundation", "Hyderabad"),
        ("Annadaan Trust", "annadaan@demo.com", "Recipient/NGO", "Annadaan Trust", "Bengaluru"),
        ("Seva Care", "seva@demo.com", "Recipient/NGO", "Seva Care", "Chennai"),
    ]
    ids = {}
    for i, (name, email, role, org, city) in enumerate(users):
        ids[email] = storage.add_record("users", {
            "name": name, "email": email, "password": auth.hash_password("demo123"),
            "role": role, "phone": f"98{i}0000{i}11"[:10], "organization": org,
            "city": city, "created_at": storage.now_str()})
    donors = [(ids[u[1]], u[0], u[4]) for u in users if u[2] == "Donor"]
    ngos = [(ids[u[1]], u[3]) for u in users if u[2] == "Recipient/NGO"]

    foods = {"Cooked Meals": ["Veg biryani", "Dal rice", "Chapati & curry"],
             "Bakery": ["Bread loaves", "Buns", "Cakes"],
             "Fruits & Vegetables": ["Mixed vegetables", "Bananas", "Apples"],
             "Dairy": ["Milk packets", "Curd tubs"],
             "Packaged Food": ["Biscuits", "Instant noodles"],
             "Grains & Pulses": ["Rice sacks", "Toor dal"],
             "Beverages": ["Fruit juice cartons"]}
    now = datetime.now()

    for n in range(70):
        created = now - timedelta(days=random.randint(1, 120), hours=random.randint(0, 20))
        donor_id, donor_name, city = random.choice(donors)
        category = random.choice(list(foods))
        qty = round(random.uniform(2, 40), 1)
        servings = int(qty * random.randint(3, 6))
        expiry = created + timedelta(hours=random.randint(6, 48))
        roll = random.random()
        status = ("Distributed" if roll < 0.55 else "Expired" if roll < 0.75
                  else "Collected" if roll < 0.80 else "Reserved" if roll < 0.87 else "Available")
        if expiry > now and status in ("Expired",):
            status = "Available"
        if status == "Available" and expiry < now:
            expiry = now + timedelta(hours=random.randint(3, 36))     # keep Available items still valid
        did = storage.add_record("donations", {
            "donor_id": donor_id, "donor_name": donor_name, "food_name": random.choice(foods[category]),
            "category": category, "quantity_kg": qty, "servings": servings, "city": city,
            "pickup_address": f"{random.randint(1, 99)}, Main Road, {city}",
            "expiry_datetime": expiry.strftime(FMT), "notes": "", "status": status,
            "created_at": created.strftime(FMT)})
        if status in ("Reserved", "Collected", "Distributed"):
            ngo_id, ngo_name = random.choice(ngos)
            requested = created + timedelta(hours=random.randint(1, 4))
            decided = requested + timedelta(minutes=random.randint(15, 240))
            rid = storage.add_record("requests", {
                "donation_id": did, "recipient_id": ngo_id, "recipient_name": ngo_name,
                "message": "We can collect within 2 hours.",
                "status": "Approved" if status == "Reserved" else status,
                "requested_at": requested.strftime(FMT), "decided_at": decided.strftime(FMT)})
            if status in ("Collected", "Distributed"):
                collected = decided + timedelta(hours=random.randint(1, 3))
                done = status == "Distributed"
                storage.add_record("distributions", {
                    "request_id": rid, "donation_id": did, "recipient_id": ngo_id,
                    "recipient_name": ngo_name, "collected_at": collected.strftime(FMT),
                    "distributed_at": (collected + timedelta(hours=1)).strftime(FMT) if done else "",
                    "people_served": servings if done else 0,
                    "distribution_location": f"Shelter home, {city}" if done else "",
                    "notes": "", "status": status})
        elif status == "Expired" and random.random() < 0.3:      # a rejected request on expired food
            ngo_id, ngo_name = random.choice(ngos)
            storage.add_record("requests", {
                "donation_id": did, "recipient_id": ngo_id, "recipient_name": ngo_name,
                "message": "", "status": "Rejected",
                "requested_at": created.strftime(FMT), "decided_at": expiry.strftime(FMT)})


if __name__ == "__main__":
    if "--reset" in sys.argv:
        for table in storage.SCHEMAS:
            if os.path.exists(storage.path_of(table)):
                os.remove(storage.path_of(table))
    storage.init_storage()
    auth.ensure_admin()
    if len(storage.load("donations")) == 0:
        seed_app_data()
        print("Demo data created.")
    else:
        print("Data already exists. Use  python seed_data.py --reset  to start fresh.")
    seed_waste_datasets()
    print("Sample waste datasets written to data/waste_datasets/")
    print("Logins:  admin@foodrescue.com / admin123   |   donor: spice@demo.com / demo123   |   NGO: hope@demo.com / demo123")
