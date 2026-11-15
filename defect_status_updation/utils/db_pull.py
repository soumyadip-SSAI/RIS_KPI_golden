"""Postgres connection (SQLAlchemy + psycopg3) built from the DB_* settings in utils/config.py (from .env)."""
import logging

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from utils import config

log = logging.getLogger(__name__)


def get_engine():
    config.require_db_settings()
    url = URL.create("postgresql+psycopg", username=config.DB_USER, password=config.DB_PASSWORD,
                     host=config.DB_HOST, port=config.DB_PORT, database=config.DB_NAME)
    return create_engine(url, connect_args={"connect_timeout": config.DB_CONNECT_TIMEOUT}, pool_pre_ping=True)


def check_connection(engine):
    """True when the database answers; the error is logged otherwise."""
    try:
        with engine.connect() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar()
        log.info("Connected to %s on %s", db, config.DB_HOST)
        return True
    except Exception as e:
        log.error("Connection to %s failed: %s: %s", config.DB_NAME, type(e).__name__, e)
        return False


def read_table(engine, schema, table):
    """Whole table as a DataFrame. dtype=object keeps values as the driver returns them: integer ids with
    NULLs stay 123 (not 123.0), which the id joins downstream rely on."""
    with engine.connect() as conn:
        result = conn.execute(text(f'SELECT * FROM "{schema}"."{table}"'))
        return pd.DataFrame(result.fetchall(), columns=list(result.keys()), dtype=object)
