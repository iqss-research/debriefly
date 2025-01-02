FROM ubuntu:22.04

# reflex backend
EXPOSE 8000
# reflex frontend
EXPOSE 3000

RUN apt-get update
RUN apt-get install -y python3
RUN apt-get install -y python3-pip
RUN python3 -m pip install --upgrade pip
RUN apt-get install -y git curl zip

WORKDIR /app
COPY . .

RUN python3 -m pip install -e .

# Download all npm dependencies and compile
RUN reflex export --no-zip

# Needed until Reflex properly passes SIGTERM on backend.
STOPSIGNAL SIGKILL

CMD reflex db init && \
    [ -d alembic ] && reflex db migrate || echo "Skipping alembic migration." && \
    python3 scripts/seed_data.py && \
    exec reflex run --env prod
