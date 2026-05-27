import os
import dotenv
import reflex as rx
from sqlmodel import select
from debriefly.reflex.backend.models import Config


def init_seed_data():

    dotenv.load_dotenv()

    with rx.session() as session:
        # A basic check to see if we need to populate anything.
        if session.exec(select(Config)).first() is None:
            print("Populating seed data..")
            data = [
                Config(
                    section="General",
                    name="BASE_URL",
                    value=os.getenv("BASE_URL", "http://localhost:3000"),
                ),
            ]
            session.add_all(data)
            session.commit()
        else:
            print("Config table not empty. Not seeding with data.")


if __name__ == "__main__":
    init_seed_data()
