import logging
import os
from requests_oauth2client import OAuth2Client, OAuth2ClientCredentialsAuth

from debriefly import config
from debriefly.qualtrics.request import QualtricsRequest

logger = logging.getLogger(__name__)


class QualtricsSession:
    def __init__(
        self,
        data_center=None,
        api_token=None,
        client_id=None,
        client_secret=None,
        openai_client=None,
    ):
        self.data_center = data_center or os.getenv("Q_DATA_CENTER")
        assert self.data_center, "data_center is required"
        self.api_token = api_token or os.getenv("Q_API_TOKEN")
        self.openai_client = openai_client

        if not self.api_token:
            client_id = client_id or os.getenv("Q_CLIENT_ID")
            client_secret = client_secret or os.getenv("Q_CLIENT_SECRET")
            assert (
                client_id and client_secret
            ), "client_id and client_secret are required"

            self.auth = OAuth2ClientCredentialsAuth(
                OAuth2Client(
                    token_endpoint=config.qualtrics.oauth2_token_endpoint,
                    client_id=client_id,
                    client_secret=client_secret,
                ),
                scope=config.qualtrics.oauth2_scope,
            )

        else:
            self.auth = None

    def __enter__(self):
        kwargs = {"headers": {"Content-Type": "application/json"}}
        if self.api_token:
            kwargs["headers"]["x-api-token"] = self.api_token
        if self.auth:
            kwargs["auth"] = self.auth
        QualtricsRequest.data_center = self.data_center
        QualtricsRequest.default_request_kwargs = kwargs
        QualtricsRequest.openai_client = self.openai_client
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        QualtricsRequest.data_center = ""
        QualtricsRequest.default_request_kwargs = {}
        QualtricsRequest.openai_client = None
