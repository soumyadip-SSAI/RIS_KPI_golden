"""DB extraction: each table in config.DB_TABLES -> config.RAW_DB_DIR/<table>/<YYYY>/<MM>/<DD>/<table>.csv

    python -m src.db_extraction        # run from the defect_status_updation folder
"""
import logging
import sys
import time
from datetime import datetime

from utils import config
from utils.db_pull import check_connection, get_engine, read_table
from utils.db_store import save_csv, table_dir

log = logging.getLogger("db_extraction")


def extract_tables(tables=None, raw_db_dir=None, when=None):
    """Pull every table and save it in today's date folder. Returns {table: saved path}.
    Raises RuntimeError when the DB cannot be reached or any table fails, so callers never work on a partial pull."""
    tables = tables or config.DB_TABLES
    raw_db_dir = raw_db_dir or config.RAW_DB_DIR
    when = when or datetime.now()
    log.info("Pulling %d tables from %s.%s -> %s", len(tables), config.DB_NAME, config.DB_SCHEMA,
             raw_db_dir / "<table>" / f"{when:%Y/%m/%d}")

    engine = get_engine()
    try:
        if not check_connection(engine):
            raise RuntimeError(f"Cannot connect to {config.DB_NAME} on {config.DB_HOST}")

        saved, failed = {}, []
        for table in tables:
            start = time.perf_counter()
            try:
                df = read_table(engine, config.DB_SCHEMA, table)
                saved[table] = save_csv(df, table_dir(raw_db_dir, table, when), table)
                log.info("%-25s %9s rows x %3d cols  (%.1fs)", table, f"{len(df):,}", len(df.columns),
                         time.perf_counter() - start)
            except Exception as e:
                failed.append(table)
                log.error("%-25s FAILED: %s: %s", table, type(e).__name__, e)
    finally:
        engine.dispose()

    if failed:
        raise RuntimeError(f"DB extraction failed for: {', '.join(failed)}")
    log.info("DB extraction done: %d/%d tables", len(saved), len(tables))
    return saved


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    try:
        extract_tables()
    except Exception:
        log.exception("Aborted")
        sys.exit(1)
