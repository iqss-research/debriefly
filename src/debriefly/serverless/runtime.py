"""ASGI entry point for AWS Lambda Web Adapter (one request per invocation)."""

import os

from debriefly.serverless.settings import load_runtime_secret


os.environ["DEBRIEFLY_LAMBDA"] = "true"
load_runtime_secret()

from reflex.config import get_config  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from debriefly.reflex import app  # noqa: E402
from debriefly.serverless.state import SqlStateStore  # noqa: E402
from debriefly.serverless.transport import register_lambda_routes  # noqa: E402


signing_key = os.environ.get("AUTH_SECRET_KEY", "")
if len(signing_key) < 32:
    raise RuntimeError("AUTH_SECRET_KEY must contain at least 32 characters")
if not os.getenv("DEBRIEFLY_LOCAL_PREVIEW") and not os.getenv(
    "DEBRIEFLY_ORIGIN_VERIFY_SECRET"
):
    raise RuntimeError("DEBRIEFLY_ORIGIN_VERIFY_SECRET is required on Lambda")

store = SqlStateStore(
    create_engine(get_config().db_url, poolclass=NullPool),
    signing_key,
    version=os.getenv("DEBRIEFLY_STATE_VERSION", "1"),
)
# Register page-load handlers and dynamic route vars without compiling assets.
# Reflex normally does this as part of `reflex run`, which Lambda bypasses.
app._apply_decorated_pages()
register_lambda_routes(app, store)
api = app.api
