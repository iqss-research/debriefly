from dotenv import load_dotenv
import os
from pprint import pprint
import requests
from requests_oauth2client import OAuth2Client, OAuth2ClientCredentialsAuth


if __name__ == "__main__":
    load_dotenv()

    oauth2client = OAuth2Client(
        token_endpoint="https://env.qualtrics.com/oauth2/token",
        client_id=os.environ["Q_CLIENT_ID"],
        client_secret=os.environ["Q_CLIENT_SECRET"],
    )

    auth = OAuth2ClientCredentialsAuth(oauth2client, scope="manage:all read:users")

    response = requests.get(
        "https://sjci.qualtrics.com/API/v3/surveys/SV_8ADyHCnFttPUPJA", auth=auth
    )
    pprint(response.json())
