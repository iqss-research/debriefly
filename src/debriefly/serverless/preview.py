"""Review the Lambda frontend locally against a separate SQLite database."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import secrets
import tempfile
import time


DYNAMIC_ROUTES = [
    (r"/edit/form/[^/]+/field/[^/]+", "/edit/form/[form_id]/field/[field_id]"),
    (r"/edit/form/[^/]+/field", "/edit/form/[form_id]/field"),
    (r"/edit/form/[^/]+", "/edit/form/[form_id]"),
    (r"/responses/[^/]+/analyze", "/responses/[form_id]/analyze"),
    (r"/responses/[^/]+", "/responses/[form_id]"),
    (r"/form/[^/]+", "/form/[form_code]"),
]


def exported_file(directory, route):
    """Resolve both forms of Next static output, with literal routes first."""
    route = "/" + route.strip("/")
    candidates = [route]
    candidates.extend(
        target for pattern, target in DYNAMIC_ROUTES if re.fullmatch(pattern, route)
    )
    for candidate in candidates:
        relative = candidate.lstrip("/") or "index"
        for name in (relative, f"{relative}.html", f"{relative}/index.html"):
            target = (directory / name).resolve()
            if target.is_relative_to(directory) and target.is_file():
                return target
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend", type=Path, default=Path("serverless/dist"))
    parser.add_argument(
        "--database",
        type=Path,
        help="Separate local SQLite file; defaults to a new temporary database",
    )
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    startup_started = time.perf_counter()
    frontend = args.frontend.resolve()
    if not (frontend / "index.html").is_file():
        parser.error("Build the frontend first: python serverless/build_frontend.py")
    from debriefly.serverless.build_info import frontend_warning

    warning = frontend_warning(frontend)
    if warning:
        print(f"WARNING: {warning}\n", flush=True)
    database = (
        args.database
        or (Path(tempfile.mkdtemp(prefix="debriefly-review-")) / "review.db")
    ).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    origin = f"http://localhost:{args.port}"
    # Override inherited deployment settings: preview never connects to RDS or
    # loads runtime secrets. The SQLite file is created explicitly for review.
    for name in (
        "DEBRIEFLY_RUNTIME_SECRET_ARN",
        "DB_USER",
        "DB_PASS",
        "DB_HOST",
        "DB_NAME",
    ):
        os.environ.pop(name, None)
    os.environ.update(
        DEBRIEFLY_LAMBDA="true",
        DEBRIEFLY_LOCAL_PREVIEW="true",
        DEBRIEFLY_ORIGIN_VERIFY_SECRET="",
        DEBRIEFLY_REQUIRE_POSTGRESQL="false",
        DEBRIEFLY_REQUIRE_DATABASE_URL="false",
        DB_URL=f"sqlite:///{database}",
        AUTH_SECRET_KEY="local-review-only-0123456789abcdef0123456789abcdef",
        AUTH_PUBLIC_URL=origin,
        AUTH_API_PUBLIC_URL="",
        AUTH_ALLOWED_ORIGINS=origin,
        AUTH_COOKIE_SECURE="false",
        AUTH_ALLOW_REGISTRATION="false",
        API_URL=origin,
        BASE_URL=origin,
        SMTP_HOST="",
        SMTP_FROM="",
        TELEMETRY_ENABLED="false",
    )

    print("[1/3] Loading the application and its dependencies...", flush=True)
    import reflex as rx
    import uvicorn
    from fastapi import HTTPException
    from fastapi.responses import FileResponse
    from sqlmodel import SQLModel, select
    from debriefly.reflex.backend.models import Config, LocalCredential, User
    from debriefly.reflex.local_auth import hash_password
    from debriefly.serverless.runtime import api, store

    print("[2/3] Preparing the separate local review database...", flush=True)
    SQLModel.metadata.create_all(store.engine)
    store.prepare()
    email = "reviewer@example.test"
    password = secrets.token_urlsafe(18)
    with rx.session() as session:
        user = session.exec(select(User).where(User.email_normalized == email)).first()
        if user is None:
            user = User(
                user_id="local-lambda-reviewer",
                email_normalized=email,
                email_verified_at=datetime.now(timezone.utc),
                role="admin",
                status="active",
            )
            session.add(user)
        credential = session.get(LocalCredential, user.user_id)
        if credential is None:
            credential = LocalCredential(user_id=user.user_id)
        credential.password_hash = hash_password(password)
        session.add(credential)
        if session.exec(select(Config)).first() is None:
            session.add(Config(section="General", name="BASE_URL", value=origin))
        session.commit()

    @api.get("/{route:path}", include_in_schema=False)
    async def static_page(route: str):
        target = exported_file(frontend, route)
        if target is None:
            raise HTTPException(404)
        return FileResponse(target, headers={"Cache-Control": "no-store"})

    print(
        f"[3/3] Starting the local server (prepared in {time.perf_counter() - startup_started:.1f}s)...",
        flush=True,
    )
    print(f"Local Lambda review: {origin}", flush=True)
    print(f"Separate review database: {database}", flush=True)
    print(f"Review account: {email}\nReview password: {password}", flush=True)
    print(
        "Email is disabled. Enter your own OpenAI key to test AI interviews.",
        flush=True,
    )
    uvicorn.run(api, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nLocal preview stopped.", flush=True)
        raise SystemExit(130) from None
