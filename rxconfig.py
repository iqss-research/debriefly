import sys
import os
import dotenv
import reflex as rx

sys.path.append("src")

dotenv.load_dotenv()
config = rx.Config(app_name="debriefly", db_url=os.getenv("DB_URL"))
