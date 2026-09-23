"""
Anonymous usage events → Postgres (analytics.events).

How it works
------------
- Off unless ANALYTICS_DSN is set (environment variable or .streamlit/secrets.toml).
  Locally without it, every call is a no-op: the app behaves exactly as before.
- log_event() only builds a row and puts it in a queue: the page never waits
  for the database.
- One background thread per server process (shared by all sessions through
  st.cache_resource) takes rows from the queue and INSERTs them.
- Any database error is logged and the event is dropped. Telemetry must never
  break the app.

What is recorded: event name, page, a random session id, host, app version and a
few small props. Never save content, business names, addresses or money.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

import streamlit as st

APP_VERSION = "3.0.0"
SCHEMA_VER = 1
VALID_HOSTS = ("hf", "render", "local")
EVENT_NAME = re.compile(r"[a-z_]{1,40}")      # same rule as the CHECK in db/001_schema.sql
QUEUE_SIZE = 1000                             # beyond this, events are dropped (DB down for long)

_SID_KEY = "_telemetry_sid"                   # session_state keys
_ONCE_KEY = "_telemetry_once"
_PAGE_KEY = "_telemetry_page"

# Placeholders are filled by the driver (never string formatting: no SQL injection).
# The app role has INSERT only, so:
# - no RETURNING (it would need SELECT);
# - ON CONFLICT without a target: "ON CONFLICT (event_id)" makes Postgres read
#   event_id to pick the unique index, which needs SELECT on that column.
#   Without a target, any unique violation (here only the primary key) is skipped.
INSERT_SQL = """
INSERT INTO analytics.events
    (event_id, ts, session_id, host, app_version, schema_ver, event, page, props)
VALUES (%s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s, %s::jsonb)
ON CONFLICT DO NOTHING
"""

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------

def _setting(name: str) -> Optional[str]:
    """Environment variable first (HF / Render), then .streamlit/secrets.toml (local)."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name)          # raises if there is no secrets file
    except Exception:
        return None


def enabled() -> bool:
    return bool(_setting("ANALYTICS_DSN"))


def current_host() -> str:
    host = _setting("ANALYTICS_HOST")
    if host in VALID_HOSTS:
        return host
    if os.environ.get("SPACE_ID"):           # set by Hugging Face Spaces
        return "hf"
    if os.environ.get("RENDER"):             # set by Render
        return "render"
    return "local"


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------

def _json_default(value):
    """numpy numbers → plain int/float (7, not "7"); anything else → text."""
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def build_row(event: str, page: Optional[str], props: dict, session_id: str,
              host: str, now: Optional[datetime] = None) -> tuple:
    """One tuple in the order of INSERT_SQL. Pure function: easy to test."""
    if not EVENT_NAME.fullmatch(event):
        raise ValueError(f"invalid event name: {event!r}")
    if host not in VALID_HOSTS:
        raise ValueError(f"invalid host: {host!r}")
    ts = now or datetime.now(timezone.utc)
    return (
        str(uuid.uuid4()),
        ts,
        session_id,
        host,
        APP_VERSION,
        SCHEMA_VER,
        event,
        page,
        json.dumps(props, default=_json_default),
    )


# ---------------------------------------------------------------------------
# writer (one per process)
# ---------------------------------------------------------------------------

def _pg_connect(dsn: str):
    import psycopg                            # imported here: not needed when telemetry is off
    return psycopg.connect(dsn, autocommit=True, connect_timeout=5)


class Writer:
    """Background thread that drains the queue into Postgres."""

    def __init__(self, dsn: str, connect: Callable = _pg_connect, start: bool = True):
        self._dsn = dsn
        self._connect = connect
        self._conn = None
        self.queue: "queue.Queue[tuple]" = queue.Queue(maxsize=QUEUE_SIZE)
        if start:
            threading.Thread(target=self._run, name="telemetry-writer", daemon=True).start()

    def put(self, row: tuple) -> None:
        try:
            self.queue.put_nowait(row)
        except queue.Full:
            log.warning("telemetry: queue full, event dropped")

    def _run(self) -> None:
        while True:
            row = self.queue.get()
            try:
                self.write(row)
            finally:
                self.queue.task_done()

    def write(self, row: tuple) -> bool:
        """Insert one row. On failure reconnect and retry once, then give up."""
        for attempt in (1, 2):
            try:
                if self._conn is None:
                    self._conn = self._connect(self._dsn)
                with self._conn.cursor() as cur:
                    cur.execute(INSERT_SQL, row)
                return True
            except Exception as e:            # connection dropped (e.g. Neon idle), DB down...
                log.warning("telemetry: insert failed (attempt %d): %s", attempt, type(e).__name__)
                self._close()
        return False

    def _close(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        except Exception:
            pass
        self._conn = None


@st.cache_resource(show_spinner=False)
def _get_writer(dsn: str) -> Writer:
    return Writer(dsn)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def session_id() -> str:
    sid = st.session_state.get(_SID_KEY)
    if sid is None:
        sid = str(uuid.uuid4())
        st.session_state[_SID_KEY] = sid
    return sid


def log_event(event: str, page: Optional[str] = None, **props) -> None:
    """Record one event. Never raises."""
    dsn = _setting("ANALYTICS_DSN")
    if not dsn:
        return
    try:
        row = build_row(event, page, props, session_id(), current_host())
        _get_writer(dsn).put(row)
    except Exception as e:
        log.warning("telemetry: event %r not logged: %s", event, e)


def log_once(key: str, event: str, page: Optional[str] = None, **props) -> None:
    """Log only the first time `key` is seen in this session.

    Streamlit reruns the whole script on every click: without this, an event
    written in the script body would be logged again at each rerun.
    """
    seen = st.session_state.setdefault(_ONCE_KEY, set())
    if key in seen:
        return
    seen.add(key)
    log_event(event, page=page, **props)


def start_session() -> None:
    """Call once at the top of the app: logs session_start for a new session."""
    log_once("session_start", "session_start")


def log_page_view(page: str) -> None:
    """Log only when the page changes, not at every rerun."""
    if st.session_state.get(_PAGE_KEY) == page:
        return
    st.session_state[_PAGE_KEY] = page
    log_event("page_view", page=page)
