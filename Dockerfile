FROM ubuntu:22.04

# reflex backend
EXPOSE 8000
# reflex frontend
EXPOSE 3000

RUN apt-get update
RUN apt-get install -y python3
RUN apt-get install -y python3-pip
RUN python3 -m pip install --upgrade pip
RUN apt-get install -y git curl zip vim

RUN useradd -m debriefly -g root
RUN mkdir /app && chown debriefly /app

USER debriefly
ENV PATH="/home/debriefly/.local/bin:/usr/local/bin:$PATH"
WORKDIR /app
COPY --chown=debriefly:root . .

RUN python3 -m pip install -e .

# Download all npm dependencies and compile
RUN reflex export --no-zip

# Needed until Reflex properly passes SIGTERM on backend.
STOPSIGNAL SIGKILL

CMD reflex db init && \
    [ -d alembic ] && reflex db migrate || echo "Skipping alembic migration." && \
    python3 scripts/seed_data.py && \
    exec reflex run --env prod
