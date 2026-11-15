"""Contract-module project master: UPC filter and project details (length, state, NH, ...)."""
import logging

import pandas as pd

from utils.io_utils import read_table_file

log = logging.getLogger(__name__)

# RIS view column -> project master column (same names as Databricks project_master_onetime)
PROJECT_COLUMNS = {
    "UPC Length(in km)": "Length-km",
    "UPC Lane Length(in km)": "Lane-km",
    "State": "State Name",
    "RO": "RO",
    "PIU": "PIU",
    "NH": "NH No.",
    "AE/IE": "AE/IE Name",
    "Contractor": "Contractor Name",
}
# PROJECT_COLUMNS outputs read as numbers; all other columns are stripped text
NUM_COLS = ["UPC Length(in km)", "UPC Lane Length(in km)"]


def _clean_text(value):
    return None if pd.isna(value) else str(value).strip()


def load_project_master(path):
    """One row per UPC (column 'upc') with the PROJECT_COLUMNS details: lengths as numbers (invalid -> NaN),
    other columns as stripped text, rows without a UPC dropped, first row kept per UPC."""
    raw = read_table_file(path)
    upc_col = next((c for c in raw.columns if str(c).lower() == "upc"), None)
    if upc_col is None:
        raise ValueError(f"No UPC column in {path}")

    missing = [src for src in PROJECT_COLUMNS.values() if src not in raw.columns]
    if missing:
        raise ValueError(f"Project master {path} is missing columns: {', '.join(missing)}")

    info = raw[[upc_col, *PROJECT_COLUMNS.values()]].copy()
    info.columns = ["upc", *PROJECT_COLUMNS]
    for col in info.columns:
        if col in NUM_COLS:
            info[col] = pd.to_numeric(info[col], errors="coerce")
        else:
            info[col] = info[col].map(_clean_text).astype("string")
    n_raw = len(info)
    info = info.dropna(subset=["upc"]).drop_duplicates("upc").reset_index(drop=True)
    log.info("Project master loaded — %s rows -> %s unique UPCs", f"{n_raw:,}", f"{len(info):,}")
    return info


def filter_project_upcs(tables, project_info, enabled):
    """Keep only UPCs present in the project master (all tables), when enabled."""
    if not enabled:
        log.warning("FILTER_BY_PROJECT_MASTER = False (utils/config.py): UPCs are NOT filtered against the project master")
        return tables
    valid_upcs = set(project_info["upc"].dropna())
    filtered = {}
    for name, df in tables.items():
        keep = df["upc"].isin(valid_upcs).fillna(False)
        log.info("  %-28s — %8s → %8s  (dropped %s rows with unknown UPC)",
                 name, f"{len(df):,}", f"{int(keep.sum()):,}", f"{int((~keep).sum()):,}")
        filtered[name] = df[keep]
    return filtered
