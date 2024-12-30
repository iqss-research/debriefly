FROM ubuntu:22.04
# FROM registry.access.redhat.com/ubi9/python-311:latest

EXPOSE 8081
# reflex backend
EXPOSE 8000
# reflex frontend
EXPOSE 3000

#RUN apk add --no-cache git gcc g++ make musl-dev python3-dev linux-headers
#RUN apk add bash
#RUN apk add lscpu
RUN apt-get update
RUN apt-get install -y python3

RUN apt-get install -y python3-pip
RUN python3 -m pip install --upgrade pip
RUN apt-get install -y git curl zip

#RUN apk add nodejs npm
#RUN apk add curl
#RUN curl -fsSL https://bun.sh/install | bash

#RUN apt-get update && apt-get install -y redis-server && rm -rf /var/lib/apt/lists/*
#ENV REDIS_URL=redis://localhost PYTHONUNBUFFERED=1

# Copy local context to `/app` inside container (see .dockerignore)
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
