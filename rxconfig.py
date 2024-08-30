import sys
import os
import reflex as rx

sys.path.append("src")


config = rx.Config(app_name="debriefly", db_url=os.getenv("DB_URL"))
