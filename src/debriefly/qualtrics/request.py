from json import loads
import logging
import requests

logger = logging.getLogger(__name__)


class QualtricsRequest:
    # Set by an enclosing QualtricsSession context-manager
    data_center = ""
    default_request_kwargs = {}
    openai_client = None

    # Meant to be overridden by subclasses
    endpoint = "whoami"
    method = "get"

    @classmethod
    def from_data(cls, data):
        return cls(data=data)

    def __init__(self, data=None):
        self.base_url = f"https://{self.data_center}.qualtrics.com/API/v3"
        self.url = self.base_url + "/" + self.endpoint

        if data is None:
            self.make_request(method=self.method)
        else:
            self.data = data

    def make_request(
        self,
        url="",
        json={},
        data=None,
        files=None,
        method="post",
        raise_for_status=True,
        endpoint_override=False,
    ):
        if (
            request_fn := {
                "get": requests.get,
                "post": requests.post,
                "put": requests.put,
            }.get(method)
        ) is None:
            raise NotImplementedError

        url = (self.base_url if endpoint_override else self.url) + "/" + url

        # create a copy so we're not modifying arguments for subsequent calls
        kwargs = self.default_request_kwargs.copy()
        # if not json was provided, no need to specify content-type
        if not json and "Content-Type" in kwargs.get("headers", {}):
            kwargs["headers"].pop("Content-Type")

        logger.debug(
            f"{method} request: {self.url} json={json} kwargs={self.default_request_kwargs}"
        )

        response = request_fn(
            url,
            json=json,
            data=data,
            files=files,
            **kwargs,
        )
        if raise_for_status:
            response.raise_for_status()

        logger.debug(f"{method} response: {response}")
        content_type = response.headers["Content-Type"]
        logger.debug(f"Content-Type: {content_type}")
        if content_type == "application/json":
            response = loads(response.text)
            # put requests have a 'meta' key, others have 'result'
            if method == "put":
                self.data = response["meta"]
            else:
                self.data = response["result"]
        else:
            content = response.content
            self.data = content
