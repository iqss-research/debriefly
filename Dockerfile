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

RUN mkdir /app
WORKDIR /app
COPY . .

# A production pod must never continue on an ephemeral, pod-local SQLite file
# because its Secret or envFrom reference was omitted.
ENV DEBRIEFLY_REQUIRE_DATABASE_URL=true

# https://stackoverflow.com/questions/58473832
RUN chgrp -R 0 /app && \
    chmod -R g=u /app && \
    chmod -R g+s /app  # reflex creates folders like .web/ etc

RUN python3 -m pip install -r requirements.txt
RUN python3 -m pip install -e . --no-deps

# Needed until Reflex properly passes SIGTERM on backend.
STOPSIGNAL SIGKILL

CMD set -eu; \
    python3 scripts/apply_schema_migrations.py; \
    python3 scripts/seed_data.py; \
    exec reflex run --env prod
