import os
import sys

import dotenv
import reflex as rx

sys.path.append("src")

from debriefly.database import database_url_from_env  # noqa: E402

dotenv.load_dotenv()
db_url = database_url_from_env(os.environ)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "AUTH_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

config = rx.Config(
    app_name="debriefly",
    db_url=db_url,
    cors_allowed_origins=allowed_origins,
)
