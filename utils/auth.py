"""Registration, login and input-validation helpers."""
import hashlib
import re
import secrets

from utils import storage
from utils.constants import ROLE_ADMIN


# ---------- password handling ----------
def hash_password(password, salt=None):
    """Store passwords as  salt$sha256(salt+password)  - never as plain text."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def verify_password(password, stored):
    if "$" not in stored:
        return False
    salt = stored.split("$")[0]
    return hash_password(password, salt) == stored


# ---------- validation ----------
def is_valid_email(email):
    return re.fullmatch(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", email.strip()) is not None


def is_valid_phone(phone):
    return re.fullmatch(r"[6-9]\d{9}", phone.strip()) is not None   # 10-digit Indian mobile


# ---------- register / login ----------
def register_user(name, email, password, confirm, role, phone, organization, city):
    """Returns (success: bool, message: str)."""
    errors = []
    if len(name.strip()) < 3:
        errors.append("Name must have at least 3 characters.")
    if not is_valid_email(email):
        errors.append("Enter a valid email address.")
    if len(password) < 6:
        errors.append("Password must have at least 6 characters.")
    if password != confirm:
        errors.append("Passwords do not match.")
    if not is_valid_phone(phone):
        errors.append("Phone must be a valid 10-digit mobile number.")
    if not city.strip():
        errors.append("City is required.")
    if errors:
        return False, " ".join(errors)

    users = storage.load("users")
    if (users["email"].str.lower() == email.strip().lower()).any():
        return False, "An account with this email already exists."

    storage.add_record("users", {
        "name": name.strip(), "email": email.strip().lower(),
        "password": hash_password(password), "role": role,
        "phone": phone.strip(), "organization": organization.strip(),
        "city": city.strip().title(), "created_at": storage.now_str(),
    })
    return True, "Registration successful! You can log in now."


def login_user(email, password):
    """Returns the user dict if credentials are correct, otherwise None."""
    users = storage.load("users")
    match = users[users["email"].str.lower() == email.strip().lower()]
    if match.empty:
        return None
    user = match.iloc[0].to_dict()
    return user if verify_password(password, user["password"]) else None


def ensure_admin():
    """Create the default admin account on first run."""
    users = storage.load("users")
    if (users["role"] == ROLE_ADMIN).any():
        return
    storage.add_record("users", {
        "name": "System Admin", "email": "admin@foodrescue.com",
        "password": hash_password("admin123"), "role": ROLE_ADMIN,
        "phone": "9000000000", "organization": "Smart Food Rescue",
        "city": "Hyderabad", "created_at": storage.now_str(),
    })
