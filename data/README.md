# Data Directory: CSV Storage Layer

This directory serves as the persistent flat-file data store for the **Food Waste Management and Redistribution** platform.

> **Strict Academic Constraint:** No SQL or relational database engine (SQLite, MySQL, PostgreSQL) is used. All persistence is handled via CSV file operations managed by `utils/storage.py`.

## Operational Tables:
- `users.csv`: Contains registered user records with salted SHA-256 password hashes, user roles (Donor, NGO, Admin), and contact details.
- `donations.csv`: Operational food donation listings, categories, quantities in kg, estimated servings, expiry datetimes, and status.
- `requests.csv`: Food requests initiated by NGOs with status (`Pending`, `Approved`, `Rejected`), requested timestamps, and decision timestamps.
- `distributions.csv`: Completed distribution records tracking people served, distribution locations, and delivery timestamps.

## Historical Datasets (`data/waste_datasets/`):
- `canteen_waste_sample.csv`: Sample historical food-waste log from a university dining hall (Date, Meal_Type, Day_Of_Week, Students_Present, Food_Prepared_kg, Food_Wasted_kg, Food_Category).
- `restaurant_wastage_sample.csv`: Sample historical food-wastage log from a restaurant (Date, Dish_Category, Quantity_Prepared, Quantity_Sold, Wastage_kg, Wastage_Reason, Unit_Price).

*Note: Historical waste datasets are strictly separated from operational donation records to prevent conflating past waste with surplus food currently available for donation.*
