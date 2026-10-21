"""
CSV storage layer  (no SQL / SQLite / MySQL is used anywhere in this project).

Every "table" is a CSV file inside the /data folder.  All other modules read
and write data ONLY through the functions in this file, so if a CSV format
changes only this file needs to be edited.
"""
import os
from datetime import datetime

import pandas as pd

from utils.constants import DATE_FMT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

# Column layout of every CSV file
SCHEMAS = {
    "users": ["user_id", "name", "email", "password", "role", "phone",
              "organization", "city", "created_at"],
    "donations": ["donation_id", "donor_id", "donor_name", "food_name", "category",
                  "quantity_kg", "servings", "city", "pickup_address",
                  "expiry_datetime", "notes", "status", "created_at"],
    "requests": ["request_id", "donation_id", "recipient_id", "recipient_name",
                 "message", "status", "requested_at", "decided_at"],
    "distributions": ["distribution_id", "request_id", "donation_id", "recipient_id",
                      "recipient_name", "collected_at", "distributed_at",
                      "people_served", "distribution_location", "notes", "status"],
}
ID_COL = {"users": "user_id", "donations": "donation_id",
          "requests": "request_id", "distributions": "distribution_id"}
PREFIX = {"users": "U", "donations": "D", "requests": "R", "distributions": "T"}


def now_str():
    """Current time as text, e.g. '2026-10-15 14:30'."""
    return datetime.now().strftime(DATE_FMT)


def path_of(table):
    return os.path.join(DATA_DIR, f"{table}.csv")


def init_storage():
    """Create the data folder and empty CSV files (with headers) if missing."""
    os.makedirs(DATA_DIR, exist_ok=True)
    for table, columns in SCHEMAS.items():
        if not os.path.exists(path_of(table)):
            pd.DataFrame(columns=columns).to_csv(path_of(table), index=False)


def load(table):
    """Read a CSV into a DataFrame. Everything is read as text; modules
    convert to numbers / dates when they need to."""
    init_storage()
    df = pd.read_csv(path_of(table), dtype=str, keep_default_na=False)
    for col in SCHEMAS[table]:
        if col not in df.columns:
            df[col] = ""
    return df[SCHEMAS[table]]


def save(table, df):
    df.to_csv(path_of(table), index=False)


def next_id(table):
    """Generate the next ID, e.g. D0001, D0002 ..."""
    df = load(table)
    prefix = PREFIX[table]
    numbers = [int(v[len(prefix):]) for v in df[ID_COL[table]]
               if v.startswith(prefix) and v[len(prefix):].isdigit()]
    return f"{prefix}{(max(numbers) if numbers else 0) + 1:04d}"


def add_record(table, record):
    """Append one record (dict). The ID is generated automatically and returned."""
    df = load(table)
    record = dict(record)
    record[ID_COL[table]] = next_id(table)
    new_row = pd.DataFrame([record], columns=SCHEMAS[table]).fillna("").astype(str)
    save(table, pd.concat([df, new_row], ignore_index=True))
    return record[ID_COL[table]]


def get_record(table, record_id):
    """Return one record as a dict, or None if not found."""
    df = load(table)
    match = df[df[ID_COL[table]] == record_id]
    return None if match.empty else match.iloc[0].to_dict()


def update_record(table, record_id, updates):
    """Change some fields of one record. `updates` is a dict."""
    df = load(table)
    mask = df[ID_COL[table]] == record_id
    for column, value in updates.items():
        df.loc[mask, column] = str(value)
    save(table, df)


def delete_record(table, record_id):
    df = load(table)
    save(table, df[df[ID_COL[table]] != record_id])
