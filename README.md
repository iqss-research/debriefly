# Debriefly

An optional AWS Lambda runtime is available for local review. It reuses the
existing Reflex pages and application handlers, with request-based streaming
and durable session snapshots. Start with [the Lambda review guide](serverless/README.md).
The separate infrastructure definition is in `../debriefly-infra/lambda/`.
This addition does not deploy or replace an existing installation.

Debriefly is a web application for designing surveys, collecting responses,
and conducting AI-assisted cognitive debriefing interviews. A hosted instance
is available at [debriefly.net](https://www.debriefly.net).

This repository contains the complete application and its Docker build
definition. It does not depend on a separate infrastructure repository. The
AWS guide below uses only this repository, standard Docker images, and services
in the AWS account owned by the deployer.

| Goal | Start here |
| --- | --- |
| Run Debriefly locally | [Local development](#local-development) |
| Understand the hosting contract | [Production hosting requirements](#production-hosting-requirements) |
| Deploy to a new AWS account | [AWS deployment with EC2 and Docker Compose](#aws-deployment-with-ec2-and-docker-compose) |
| Update an installation | [Updates and backups](#updates-and-backups) |

## Features

- Design and publish cognitive debriefing surveys.
- Collect participant responses.
- Run AI-assisted debriefing chats against survey responses.
- Embed Debriefly workflows in Qualtrics.
- Use local email-and-password authentication with verification and password
  reset.
- Let each researcher configure their own OpenAI API key.

## Before publishing a public fork

Review the application for organization-specific content before publishing or
deploying a fork:

- `src/debriefly/reflex/pages/index.md` contains the hosted-service URL.
- `src/debriefly/qualtrics/embed_snippet.js` and
  `src/debriefly/qualtrics/full_survey_embed_snippet.js` contain example URLs.
- `src/debriefly/reflex/pages/terms_of_service.md` and
  `src/debriefly/reflex/pages/privacy_statement.md` contain service-owner legal
  text that must describe the new operator accurately.
- `src/debriefly/reflex/pages/feedback.py` contains the feedback recipient.
  Update `tests/test_feedback.py` when changing it.
- Legacy migration documentation and rollback workflows should be reviewed and
  removed if they are not useful to public users.

> [!IMPORTANT]
> The current feedback page sends the signed-in user's account email and ID to
> the recipient defined in `feedback.py`. Change or disable that feature before
> deploying a fork; otherwise user data will be sent to the original project's
> recipient.

The package metadata currently identifies the project as MIT-licensed, but
this repository does not yet contain a root `LICENSE` file. Add the intended
license before calling a public distribution open source. Also scan the full
Git history—not only the current files—for credentials, user exports, database
files, and other private data before making the repository public.

## Local development

### Prerequisites

- Python 3.10 or newer; Python 3.12 is recommended
- Git
- `pip` or [`uv`](https://docs.astral.sh/uv/)

### Install

```sh
git clone https://github.com/iqss-research/debriefly.git
cd debriefly
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

With `uv`:

```sh
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e . --no-deps
```

### Configure and run

```sh
cp .env.sample .env
openssl rand -hex 32
```

Use the generated value for `AUTH_SECRET_KEY`. Keep the local URLs and ports
from `.env.sample`: the frontend runs on port 3000 and the backend on port
8000. Configure SMTP if registration, verification, password reset, or
feedback email needs to work locally.

Never commit `.env`, credentials, API keys, database files, or exported user
data.

Start Debriefly:

```sh
./debriefly
```

The helper initializes and migrates a local SQLite database, adds seed data,
and starts Reflex with hot reload. Open
[http://localhost:3000](http://localhost:3000). After signing in, use
**OpenAI Key** in the sidebar to save a standard OpenAI API key for debriefing
chats.

### Tests and migrations

```sh
pre-commit run --all-files
pytest
```

When a model change creates an Alembic revision, review it and commit it under
`alembic/versions/`. Production startup applies every committed migration.

## Production hosting requirements

Debriefly can run anywhere that provides a Linux container, PostgreSQL, HTTPS,
SMTP, and a reverse proxy with WebSocket support. These requirements describe
the existing container runtime. The optional [Lambda runtime](serverless/README.md)
uses streamed HTTP events and a separate infrastructure proposal instead.

### Container behavior

Build the application image directly from this repository:

```sh
docker build --tag debriefly:local .
```

The `Dockerfile`:

- exposes the Reflex frontend on port 3000 and backend on port 8000;
- requires PostgreSQL in production;
- applies the committed Alembic migrations at startup;
- seeds `BASE_URL` only when the configuration table is empty; and
- starts Reflex in production mode.

The first start can take several minutes because Reflex builds the frontend at
runtime. Give the container a generous startup grace period. Run only one
application replica initially: migrations run during startup, and Reflex state
is process-local unless a separate Redis-based scaling design is added and
tested.

### Reverse-proxy routing

Serve both application ports through one canonical HTTPS origin. Do not expose
ports 3000 or 8000 directly to the internet.

| Request path | Destination | Notes |
| --- | --- | --- |
| `/_event*` | Backend, port 8000 | Engine.IO polling, WebSockets, and authentication POST routes |
| `/_upload*` | Backend, port 8000 | Upload requests; allow appropriately sized bodies |
| `/ping` | Backend, port 8000 | Backend liveness only |
| Everything else | Frontend, port 3000 | Pages and frontend assets |

The proxy must preserve the request host and forwarded protocol, support
WebSocket upgrades, and use timeouts long enough for interviews and uploads.
`/ping` does not test PostgreSQL, SMTP, or OpenAI, and this repository does not
provide `/health` or `/ready` endpoints. Check the frontend separately.

### Production environment

Use one canonical URL such as `https://app.example.org` for all five URL and
origin settings:

```dotenv
API_URL=https://app.example.org
DEPLOY_URL=https://app.example.org
BASE_URL=https://app.example.org
AUTH_PUBLIC_URL=https://app.example.org
AUTH_API_PUBLIC_URL=
AUTH_ALLOWED_ORIGINS=https://app.example.org
```

`API_URL` is compiled into the Reflex frontend and must point to the public
same-origin backend route. Leave `AUTH_API_PUBLIC_URL` empty in a same-origin
production deployment.

Required production settings are:

| Variable | Purpose |
| --- | --- |
| `DB_URL` | Preferred PostgreSQL connection URL. URL-encode credentials and use provider-appropriate TLS verification. |
| `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_HOST` | Supported alternative to `DB_URL`; all four are required together. |
| `AUTH_SECRET_KEY` | Independent unpredictable value of at least 32 characters. Keep it stable. |
| `AUTH_PUBLIC_URL` | Canonical public HTTPS URL. |
| `AUTH_ALLOWED_ORIGINS` | Comma-separated exact origins allowed to authenticate and connect. Do not use `*`. |
| `AUTH_COOKIE_SECURE` | Must be `true` for non-local deployments. |
| `AUTH_ALLOW_REGISTRATION` | Explicit launch policy: `true` or `false`. |
| `SMTP_HOST`, `SMTP_FROM` | Required for registration, verification, password reset, and feedback delivery. |
| `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` | SMTP transport and credentials. |
| `SMTP_STARTTLS`, `SMTP_SSL` | Select STARTTLS or implicit TLS, never both. |

Useful optional settings include `AUTH_SESSION_HOURS`, `AUTH_TOKEN_HOURS`,
`AUTH_PASSWORD_HASH_CONCURRENCY`, `AUTH_ISSUER`, `DB_POOL_SIZE`,
`DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, `OPENAI_MODEL`, and
`TELEMETRY_ENABLED`.

Researchers save their own standard OpenAI API keys through **OpenAI Key** in
the application. Do not rely on a global `OPENAI_API_KEY` as the hosted-user
credential flow. User keys, authentication data, surveys, responses, and chat
transcripts are stored in PostgreSQL, so database access and backups are
sensitive.

## AWS deployment with EC2 and Docker Compose

This is the simplest complete AWS deployment that uses only this public
repository. It creates a single-host installation:

```text
Internet
   |
   v
Caddy on EC2 (ports 80/443, automatic HTTPS)
   |-- normal pages ----------------------> Debriefly :3000
   `-- /_event*, /_upload*, /ping --------> Debriefly :8000
                                                |
                                                v
                                      PostgreSQL container
```

This design is suitable for a small installation but is not highly available.
For higher availability, use managed PostgreSQL and a container platform as
described in [Managed AWS alternative](#managed-aws-alternative).

### 1. Create the AWS host

In a new AWS account:

1. Protect the root account with MFA and use an administrator role or IAM
   Identity Center for deployment work. Do not create root access keys.
2. Create an EC2 instance running a currently supported Ubuntu LTS release. A
   `t3.medium`-class instance with 4 GiB RAM and at least 30 GiB of encrypted
   gp3 storage is a reasonable starting point; measure and resize for actual
   traffic.
3. Attach an Elastic IP so the public address survives instance replacement or
   stop/start operations.
4. Allow inbound TCP 80 and 443. Use
   [AWS Systems Manager Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
   for administration, or restrict SSH port 22 to known administrator IPs. Do not
   allow public access to ports 3000, 8000, or 5432.
5. Point an `A` record for the selected domain to the Elastic IP. Add an `AAAA`
   record only when IPv6 is configured end to end.
6. Install Docker Engine and the Compose plugin using the current
   [Docker installation guide for Ubuntu](https://docs.docker.com/engine/install/ubuntu/).

Caddy needs the domain to resolve to this host and ports 80/443 to be reachable
before it can obtain a public certificate. Caddy manages HTTPS certificates
automatically for valid hostnames; see its
[Automatic HTTPS documentation](https://caddyserver.com/docs/automatic-https).

Use the [AWS Pricing Calculator](https://calculator.aws/) for the selected
Region and instance type. Include the instance, EBS volumes and snapshots,
Elastic IP pricing, DNS, data transfer, SMTP, monitoring, and OpenAI usage.

### 2. Clone and customize Debriefly

Connect to the instance, select a reviewed release tag or commit, and make the
organization-specific changes listed in
[Before publishing a public fork](#before-publishing-a-public-fork):

```sh
git clone https://github.com/iqss-research/debriefly.git
cd debriefly
git fetch --tags
git checkout PASTE_REVIEWED_RELEASE_TAG_OR_COMMIT
```

For a fork, clone the fork instead and keep the upstream project as a separate
Git remote.

### 3. Create the production environment

Generate two different secrets:

```sh
openssl rand -hex 32
openssl rand -hex 32
```

Create `.env.production`, set its mode to `0600`, and replace every placeholder
below. Repeat the canonical domain exactly; do not leave `example.org` values
in a real deployment.

```dotenv
DOMAIN=app.example.org

POSTGRES_DB=debriefly
POSTGRES_USER=debriefly
POSTGRES_PASSWORD=PASTE_FIRST_RANDOM_VALUE

API_URL=https://app.example.org
DEPLOY_URL=https://app.example.org
BASE_URL=https://app.example.org

AUTH_SECRET_KEY=PASTE_SECOND_RANDOM_VALUE
AUTH_PUBLIC_URL=https://app.example.org
AUTH_API_PUBLIC_URL=
AUTH_ALLOWED_ORIGINS=https://app.example.org
AUTH_COOKIE_SECURE=true
AUTH_ALLOW_REGISTRATION=true
AUTH_SESSION_HOURS=168
AUTH_TOKEN_HOURS=48
AUTH_PASSWORD_HASH_CONCURRENCY=1
AUTH_ISSUER=debriefly-local

SMTP_HOST=smtp.example.org
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_SSL=false
SMTP_USERNAME=replace-me
SMTP_PASSWORD=replace-me
SMTP_FROM="Debriefly <no-reply@example.org>"

DB_POOL_SIZE=5
DB_MAX_OVERFLOW=0
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

OPENAI_MODEL=gpt-4o-mini
TELEMETRY_ENABLED=false
```

Protect the file:

```sh
chmod 0600 .env.production
```

`.env.production` is excluded by this repository's Git and Docker ignore
rules. Keep another recoverable copy in an approved secret manager. Do not
send it through chat, tickets, or logs.

For SMTP on AWS, Amazon SES is one option. A new SES account or Region may be
in the [SES sandbox](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html)
and unable to send to arbitrary recipients until production access is approved.
Verify the sender identity and required DNS records before launch.

### 4. Create the Compose definition

Create `compose.production.yaml` beside the application `Dockerfile`:

```yaml
name: debriefly

services:
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:?set POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER:?set POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 10

  app:
    build:
      context: .
    restart: unless-stopped
    env_file:
      - .env.production
    environment:
      DB_HOST: db
      DB_NAME: ${POSTGRES_DB:?set POSTGRES_DB}
      DB_USER: ${POSTGRES_USER:?set POSTGRES_USER}
      DB_PASS: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}
    depends_on:
      db:
        condition: service_healthy
    expose:
      - "3000"
      - "8000"
    healthcheck:
      test:
        - CMD-SHELL
        - >-
          curl --fail --silent http://localhost:8000/ping >/dev/null &&
          curl --fail --silent http://localhost:3000/ >/dev/null
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 15m

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    environment:
      DOMAIN: ${DOMAIN:?set DOMAIN}
    depends_on:
      app:
        condition: service_healthy
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config

volumes:
  postgres_data:
  caddy_data:
  caddy_config:
```

The database and application ports are exposed only to the private Compose
network. The named PostgreSQL volume lives on the instance's encrypted EBS
storage.

### 5. Create the HTTPS reverse proxy

Create `Caddyfile` beside the Compose file:

```caddyfile
{$DOMAIN} {
    encode zstd gzip

    route {
        @backend path /_event* /_upload* /ping
        reverse_proxy @backend app:8000
        reverse_proxy app:3000
    }
}
```

Caddy's reverse proxy supports WebSockets and preserves the request URI. See
the [`reverse_proxy` documentation](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)
when adding custom upload limits, trusted proxies, or timeouts.

### 6. Start the system

Validate the Compose model without printing resolved secrets, build the image,
and start the services:

```sh
docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  config --quiet

docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  build --pull

docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  up --detach
```

Watch startup and certificate issuance:

```sh
docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  ps

docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  logs --follow app caddy
```

The first application start may remain in `health: starting` while Reflex
builds the frontend. Investigate logs rather than repeatedly restarting it.

### 7. Verify the deployment

Set the canonical URL in the operator shell:

```sh
APP_URL=https://app.example.org
```

Check the frontend, backend, and Engine.IO polling endpoint:

```sh
curl --fail --show-error --silent "$APP_URL/" > /dev/null
curl --fail --show-error --silent "$APP_URL/ping"
curl --fail --show-error --silent \
  --header "Origin: $APP_URL" \
  "$APP_URL/_event/?EIO=4&transport=polling"
```

The Engine.IO response should begin with `0{`. In a browser, confirm a real
WebSocket connection and then test:

- registration, email verification, sign-in, sign-out, and password reset;
- survey creation, editing, public response, and completion;
- debriefing chat using a researcher's saved OpenAI API key;
- feedback delivery to the recipient configured in the source;
- every Qualtrics integration used by the installation; and
- persistence after restarting both the app and database containers.

On a fresh database, keep registration enabled until at least one user has
verified their email. To close registration later, set
`AUTH_ALLOW_REGISTRATION=false` and recreate the application container:

```sh
docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  up --detach --force-recreate app
```

Self-registered accounts receive the `user` role. The application currently
has no supported first-admin bootstrap; `/admin` and `/config` require a user
whose database role is `admin`. Normal researcher and participant workflows do
not require those pages. A deployment that needs them should add and review an
auditable one-time promotion command rather than exposing a public promotion
route.

### Managed AWS alternative

For a multi-host or managed design, use:

- ECR for the image;
- one ECS/Fargate task exposing container ports 3000 and 8000;
- an Application Load Balancer with two `ip` target groups attached to that
  service;
- a default listener action to port 3000 and higher-priority path rules for
  `/_event*`, `/_upload*`, and `/ping` to port 8000;
- RDS for PostgreSQL in private subnets;
- Secrets Manager or SSM Parameter Store for runtime secrets;
- ACM for the HTTPS certificate, Route 53 or another DNS provider, and
  CloudWatch for logs and alarms.

AWS documents both
[multiple target groups for one ECS service](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/register-multiple-targetgroups.html)
and [native WebSocket support in Application Load Balancers](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-listeners.html).
Creating an ECS service with multiple target groups requires an API, CLI,
CloudFormation, CDK, or Terraform workflow; this repository does not provide
that infrastructure automation.

Start with one task because migrations and in-memory Reflex state have not
been documented here for horizontal scaling. Before adding replicas, move
migrations to a single deployment job and design and test shared Redis state,
database pool limits, health checks, and rollout behavior.

## Updates and backups

### Back up PostgreSQL

Create a logical backup before every update that may change the schema:

```sh
backup_dir="$HOME/debriefly-backups"
mkdir -p "$backup_dir"
chmod 0700 "$backup_dir"

docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  exec -T db \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
  > "$backup_dir/debriefly-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

Copy backups off the EC2 instance to encrypted storage, apply retention rules,
and regularly prove that a different host can restore them. An EBS volume or
snapshot alone is not a complete backup and recovery process.

### Update the application

Review the release and migrations, back up the database, and then rebuild from
an immutable tag or commit:

```sh
git fetch --tags
git checkout PASTE_REVIEWED_RELEASE_TAG_OR_COMMIT

docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  build --pull

docker compose \
  --env-file .env.production \
  --file compose.production.yaml \
  up --detach
```

Startup applies Alembic migrations before serving the application. Repeat the
deployment checks and inspect logs. Do not run an Alembic downgrade during an
incident unless the exact downgrade path has been tested. An older image may
not work with a newer schema; recovery may require a compatible forward fix or
a separately planned database restore.

Changing an environment secret does not alter an already running container.
After updating `.env.production`, recreate the affected service and test the
feature before revoking the old credential. Rotating `AUTH_SECRET_KEY`
invalidates sessions and outstanding verification/reset links.

## Security and operations

Before storing important data:

- keep the operating system, Docker, base images, Python dependencies, and
  PostgreSQL patched;
- expose only ports 80 and 443 publicly and use SSM or tightly restricted SSH;
- encrypt EBS volumes, database backups, and off-host backup storage;
- use unique secrets and a dedicated least-privileged database role;
- configure PostgreSQL TLS with server identity verification when the database
  is on another host or managed service;
- add CloudWatch alarms, external uptime monitoring, centralized logs, an AWS
  Budget, and Cost Anomaly Detection;
- consider AWS WAF or another edge rate limiter because application rate limits
  are per backend process;
- test SMTP delivery, database restoration, credential rotation, and complete
  instance recovery; and
- document who owns DNS, SMTP, backups, security response, and AWS access.

The single-EC2 guide has planned and unplanned downtime when the host or app is
restarted. Use the managed design when availability requirements justify the
additional operational complexity.

## Troubleshooting

- **The frontend loads but buttons or live updates fail:** verify `API_URL`,
  `AUTH_ALLOWED_ORIGINS`, and the Caddy `/_event*` route. Inspect the browser's
  Engine.IO polling and WebSocket requests.
- **Authentication reports a configuration error:** verify the canonical HTTPS
  URL is present in `AUTH_PUBLIC_URL` and `AUTH_ALLOWED_ORIGINS`, the cookie is
  secure, and `AUTH_SECRET_KEY` is at least 32 characters.
- **Registration or password reset email does not arrive:** verify the sender
  identity, SMTP TLS mode, credentials, provider logs, and SES sandbox status
  when applicable.
- **The app repeatedly restarts during first boot:** allow time for the Reflex
  frontend build and inspect app logs for migration, memory, or compilation
  errors.
- **PostgreSQL is unavailable:** inspect the database container, volume,
  credentials, free disk space, and app-to-database network path.
- **A domain change does not update generated links:** `BASE_URL` is seeded only
  into an empty configuration table. Update the stored value through a reviewed
  admin or migration workflow as well as changing the environment and proxy.
- **Caddy cannot issue a certificate:** verify public DNS, inbound ports 80 and
  443, and that no other process is using those ports.

## Contributing

Run the full checks before opening a pull request:

```sh
pre-commit run --all-files
pytest
```

Keep migrations, tests, configuration examples, and deployment documentation
in the same change when their behavior is coupled.
