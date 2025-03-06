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
                    section="Azure",
                    name="AZURE_OPENAI_API_KEY",
                    value=os.getenv("AZURE_OPENAI_API_KEY", ""),
                ),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_DEPLOYMENT_MODEL",
                    value=os.getenv("AZURE_OPENAI_DEPLOYMENT_MODEL", "gpt-4o-mini"),
                ),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_ENDPOINT",
                    value=os.getenv(
                        "AZURE_OPENAI_ENDPOINT",
                        "https://cognitivedebriefing.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2023-03-15-preview",
                    ),
                ),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_SEARCH_ENDPOINT",
                    value=os.getenv(
                        "AZURE_OPENAI_SEARCH_ENDPOINT",
                        "https://ai-search-cognitivedebriefing.search.windows.net",
                    ),
                ),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_SEARCH_KEY",
                    value=os.getenv("AZURE_OPENAI_SEARCH_KEY", ""),
                ),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_API_VERSION",
                    value=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                ),
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
