import sys
import os
import dotenv
import reflex as rx

sys.path.append("src")

dotenv.load_dotenv()
db_user, db_pass, db_name, db_host = (
    os.getenv("DB_USER"),
    os.getenv("DB_PASS"),
    os.getenv("DB_NAME"),
    os.getenv("DB_HOST"),
)
db_url = os.getenv("DB_URL") or f"postgresql://{db_user}:{db_pass}@{db_host}/{db_name}"

# Fall back on sqlite if we got nothing
if db_url is None or db_name is None:
    db_url = "sqlite:///debriefly.db"

config = rx.Config(app_name="debriefly", db_url=db_url)
