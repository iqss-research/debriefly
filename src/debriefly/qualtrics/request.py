from json import loads
import logging
import os
import requests

logger = logging.getLogger(__name__)


class QualtricsRequest:
    # Set by an enclosing QualtricsSession context-manager
    default_request_kwargs = {}
    openai_client = None

    # Meant to be overridden by subclasses
    endpoint = "whoami"
    method = "get"

    @classmethod
    def from_data(cls, data):
        return cls(data=data)

    def __init__(self, data_center=None, api_token=None, data=None):
        data_center = data_center or os.getenv("Q_DATA_CENTER")

        self.data_center = data_center
        self.api_token = api_token or os.getenv("Q_API_TOKEN")
        self.url = f"https://{data_center}.qualtrics.com/API/v3/{self.endpoint}"

        if data is None:
            self.make_request(method=self.method)
        else:
            self.data = data

    def make_request(self, url="", json={}, method="post", raise_for_status=True):
        if (
            request_fn := {"get": requests.get, "post": requests.post}.get(method)
        ) is None:
            raise NotImplementedError

        response = request_fn(
            self.url + "/" + url,
            json=json,
            **self.default_request_kwargs,
        )
        if raise_for_status:
            response.raise_for_status()
        response = loads(response.text)

        logger.debug(
            f"{method} request: {self.url} json={json} kwargs={self.default_request_kwargs}"
        )
        logger.debug(f"{method} response: {response}")

        self.data = response["result"]
