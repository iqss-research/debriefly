import reflex as rx
from sqlmodel import select
from debriefly.reflex.backend.models import Config


def init_seed_data():
    with rx.session() as session:
        if session.exec(select(Config)).first() is None:
            print("Populating seed data..")
            data = [
                Config(section="Azure", name="AZURE_OPENAI_API_KEY", value=""),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_DEPLOYMENT_MODEL",
                    value="gpt-4o-mini",
                ),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_ENDPOINT",
                    value="https://cognitivedebriefing.openai.azure.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2023-03-15-preview",
                ),
                Config(
                    section="Azure",
                    name="AZURE_OPENAI_SEARCH_ENDPOINT",
                    value="https://ai-search-cognitivedebriefing.search.windows.net",
                ),
                Config(section="Azure", name="AZURE_OPENAI_SEARCH_KEY", value=""),
                Config(
                    section="Azure", name="AZURE_OPENAI_API_VERSION", value="2024-02-01"
                ),
                Config(
                    section="General", name="BASE_URL", value="https://debriefly.net"
                ),
            ]
            session.add_all(data)
            session.commit()
        else:
            print("Config table not empty. Not seeding with data.")


if __name__ == "__main__":
    init_seed_data()
