"""Signed, short-lived Reflex snapshots in the existing application database.

Reflex 0.5.10 excludes children and parents from pickling. Persist every node
separately and rebuild the graph rather than silently discarding substates.
Snapshots are internal server data, never supplied or downloaded by a browser.
"""

from contextlib import contextmanager
import hashlib
import hmac
import threading
import time

import dill
from sqlalchemy import (
    BigInteger,
    Column,
    LargeBinary,
    MetaData,
    String,
    Table,
    delete,
    insert,
    select,
    text,
    update,
)


metadata = MetaData()
snapshots = Table(
    "lambda_reflex_state",
    metadata,
    Column("token", String(64), primary_key=True),
    Column("payload", LargeBinary, nullable=False),
    Column("expires_at", BigInteger, nullable=False, index=True),
)


class StateBusy(RuntimeError):
    """A request for this browser tab is already running."""


def serialize_tree(root) -> bytes:
    def collect(node):
        return (
            dill.dumps(node, byref=True),
            {name: collect(child) for name, child in node.substates.items()},
        )

    return dill.dumps(collect(root), byref=True)


def deserialize_tree(payload: bytes):
    def restore(saved, parent=None):
        blob, children = saved
        node = dill.loads(blob)
        node.parent_state = parent
        node.substates = {
            name: restore(child, node) for name, child in children.items()
        }
        return node

    return restore(dill.loads(payload))


class SqlStateStore:
    """One transaction and a nonblocking PostgreSQL advisory lock per event.

    The lock also covers the first request before any snapshot row exists.
    PostgreSQL releases it automatically if Lambda is killed or disconnected.
    SQLite's local lock is only for the single-process review server and tests.
    """

    def __init__(self, engine, signing_key, version="1", ttl_seconds=86400):
        self.engine = engine
        self.signing_key = (
            signing_key.encode() if isinstance(signing_key, str) else signing_key
        )
        self.version = version
        self.ttl_seconds = ttl_seconds
        self._sqlite_lock = threading.Lock()

    def prepare(self):
        """Explicit setup command only; never run DDL during Lambda startup."""
        metadata.create_all(self.engine)

    def _key(self, token):
        return hashlib.sha256(f"{self.version}:{token}".encode()).hexdigest()

    def _sign(self, key, payload):
        return hmac.digest(self.signing_key, key.encode() + payload, "sha256") + payload

    def _load(self, key, payload):
        signature, body = bytes(payload[:32]), bytes(payload[32:])
        expected = hmac.digest(self.signing_key, key.encode() + body, "sha256")
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid state snapshot signature")
        return deserialize_tree(body)

    @contextmanager
    def modify(self, token, state_class):
        key = self._key(token)
        local_lock = self.engine.dialect.name == "sqlite"
        if local_lock and not self._sqlite_lock.acquire(blocking=False):
            raise StateBusy("Another request is running")
        try:
            with self.engine.begin() as connection:
                if self.engine.dialect.name == "postgresql":
                    lock_id = int.from_bytes(bytes.fromhex(key)[:8], "big", signed=True)
                    if not connection.execute(
                        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": lock_id}
                    ).scalar_one():
                        raise StateBusy("Another request is running")
                elif not local_lock:
                    raise ValueError("Lambda snapshots require PostgreSQL")
                row = (
                    connection.execute(
                        select(snapshots).where(snapshots.c.token == key)
                    )
                    .mappings()
                    .first()
                )
                now = int(time.time())
                state = (
                    self._load(key, row["payload"])
                    if row is not None and row["expires_at"] > now
                    else state_class(_reflex_internal_init=True)
                )
                yield state
                payload = self._sign(key, serialize_tree(state))
                values = {
                    "payload": payload,
                    "expires_at": int(time.time()) + self.ttl_seconds,
                }
                if row is None:
                    connection.execute(insert(snapshots).values(token=key, **values))
                else:
                    connection.execute(
                        update(snapshots)
                        .where(snapshots.c.token == key)
                        .values(**values)
                    )
        finally:
            if local_lock:
                self._sqlite_lock.release()

    def cleanup(self):
        """Maintenance command: remove expired snapshots, never business data."""
        with self.engine.begin() as connection:
            return connection.execute(
                delete(snapshots).where(snapshots.c.expires_at <= int(time.time()))
            ).rowcount
