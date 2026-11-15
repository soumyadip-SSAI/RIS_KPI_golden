"""DB tables (udm_defect_reference, dlm_defect_case) from the snapshots written by kpi_creation/db_data_extraction:
RAW_DB_DIR/<table>/<YYYY>/<MM>/<DD>/<table>.csv|.parquet — the latest one is used, unless a file is given
explicitly (DLM_DEFECT_CASE_FILE / UDM_DEFECT_REFERENCE_FILE in utils/config.py).
"""
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from utils.io_utils import read_text_csv

log = logging.getLogger(__name__)

SNAPSHOT_SUFFIXES = (".csv", ".parquet")


def latest_snapshot(raw_dir, table):
    """Path of the newest <YYYY>/<MM>/<DD>/<table>.* snapshot of the table."""
    snapshots = []
    for path in (Path(raw_dir) / table).glob(f"*/*/*/{table}.*"):
        if path.suffix not in SNAPSHOT_SUFFIXES:
            continue
        try:
            snapshots.append((date(*map(int, path.parent.parts[-3:])), path))
        except ValueError:
            continue  # not a date folder
    if not snapshots:
        raise FileNotFoundError(f"No snapshot of {table} in {Path(raw_dir) / table} — run kpi_creation/db_data_extraction first")
    return max(snapshots)[1]


def read_db_table(path):
    """All columns as text, empty cells as null (as the DB fetch used to return them)."""
    path = Path(path)
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
        return df.astype("string").astype(object).where(df.notna(), None)
    return read_text_csv(path, empty_as_null=True)


def load_db_tables(raw_dir, files):
    """{table: DataFrame}; files maps table -> explicit path (None = latest snapshot in raw_dir)."""
    tables = {}
    for table, path in files.items():
        path = Path(path) if path else latest_snapshot(raw_dir, table)
        tables[table] = read_db_table(path)
        log.info("Loaded %-22s %8s rows from %s", table, f"{len(tables[table]):,}", path)
    return tables
