import os
from dotenv import load_dotenv

# Force reload from .env
load_dotenv(override=True)

pin = os.getenv("ADMIN_PIN")
print(f"Loaded PIN: '{pin}'")

try:
    import config  # noqa: F401  (import check only)
    print("Config loaded successfully")
except Exception as e:
    print(f"Error loading config: {e}")
