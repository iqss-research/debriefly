"""Load deployment secrets before importing Reflex or resolving its database."""

import json
import os


def load_runtime_secret():
    arn = os.getenv("DEBRIEFLY_RUNTIME_SECRET_ARN")
    if not arn:
        return
    import boto3

    result = boto3.client("secretsmanager").get_secret_value(SecretId=arn)
    values = json.loads(result["SecretString"])
    allowed = {
        "DB_URL",
        "DB_USER",
        "DB_PASS",
        "DB_HOST",
        "DB_NAME",
        "AUTH_SECRET_KEY",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_STARTTLS",
        "SMTP_SSL",
    }
    if not isinstance(values, dict) or any(
        name not in allowed or not isinstance(value, str)
        for name, value in values.items()
    ):
        raise ValueError("Runtime secret must contain supported string settings only")
    os.environ.update(values)
