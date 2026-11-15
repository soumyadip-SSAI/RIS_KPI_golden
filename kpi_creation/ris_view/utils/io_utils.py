"""Reading the silver / reference tables and writing CSV outputs, for all three steps.

Loaders per step (each normalises the data the way its original pipeline did):
  load_silver_table  silver_table_update  every column as raw text, so the table is written back unchanged
  load_table         intermediate_logic   phase / cycle as '2' (not '2.0'), upc as text; optional tables
  load_defect_table  ris_view             as load_table, plus detected_on as a date; can read only some columns
  load_intermediate  ris_view             final_intermediate.csv
"""
import logging
from functools import partial
from pathlib import Path

import pandas as pd

from utils.helpers import to_date, to_str_id

log = logging.getLogger(__name__)

_READERS = {
    ".parquet": pd.read_parquet,
    ".csv": partial(pd.read_csv, low_memory=False),
    ".xlsx": pd.read_excel,
    ".xls": pd.read_excel,
}
# keyword each reader uses to read only some columns
_COLUMNS_ARG = {".parquet": "columns", ".csv": "usecols", ".xlsx": "usecols", ".xls": "usecols"}


# --- Generic ---

def read_table_file(path, columns=None):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = path.suffix.lower()
    try:
        reader = _READERS[suffix]
    except KeyError:
        raise ValueError(f"Unsupported file type '{path.suffix}' for {path}") from None
    return reader(path, **({_COLUMNS_ARG[suffix]: columns} if columns else {}))


def find_table_file(directory, name):
    """Return <directory>/<name>.<ext> for the first supported extension that exists."""
    for ext in _READERS:
        candidate = Path(directory) / f"{name}{ext}"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"No {name}.(parquet|csv|xlsx) found in {directory}")


def read_text_csv(path, empty_as_null=False):
    """CSV with every column as text. empty_as_null=False keeps empty cells as '' (round-trips exactly)."""
    return pd.read_csv(path, dtype=str, keep_default_na=empty_as_null, na_filter=empty_as_null,
                       encoding="utf-8-sig")


def load_columns(directory, name, columns):
    """Only the given columns of <directory>/<name>.* (keeps large tables like master_cracking light)."""
    path = find_table_file(directory, name)
    df = read_table_file(path, columns)[columns]
    log.info("Loaded %-30s rows: %s (from %s)", path.name, f"{len(df):,}", Path(directory).name)
    return df


def save_csv(df, output_dir, name):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{name}.csv"
    df.to_csv(path, index=False)
    log.info("Saved %s — %s rows", path, f"{len(df):,}")
    return path


# --- silver_table_update ---

def load_silver_table(input_dir, name):
    """Silver table as raw text (CSV) so every existing value is written back unchanged
    (no 100 -> 100.0 or date re-formatting); only the status columns are added."""
    path = find_table_file(input_dir, name)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else read_text_csv(path)
    log.info("Loaded %-30s rows: %s", path.name, f"{len(df):,}")
    return df


# --- intermediate_logic ---

def load_table(input_dir, name, optional=False, columns=()):
    """Load <input_dir>/<name>.*; with optional=True a missing file gives an empty table with `columns`."""
    try:
        path = find_table_file(input_dir, name)
    except FileNotFoundError:
        if not optional:
            raise
        log.warning("%s not found in %s — treated as an empty table", name, input_dir)
        return pd.DataFrame({col: pd.Series(dtype="string") for col in columns})
    df = read_table_file(path)
    # The notebook joined on phase/cycle; compare them as strings ('2.0' -> '2') across sources
    for col in ("phase", "cycle"):
        if col in df.columns:
            df[col] = to_str_id(df[col])
    if "upc" in df.columns:
        df["upc"] = df["upc"].astype("string")
    log.info("Loaded %-30s rows: %s", path.name, f"{len(df):,}")
    return df


# --- ris_view ---

def _normalize_keys(df):
    # Compare phase/cycle as strings ('2.0' -> '2'), upc as text and detected_on as a date
    # (CSV sources give text dates) across all sources
    for col in ("phase", "cycle"):
        if col in df.columns:
            df[col] = to_str_id(df[col])
    if "upc" in df.columns:
        df["upc"] = df["upc"].astype("string")
    if "detected_on" in df.columns:
        df["detected_on"] = to_date(df["detected_on"])
    return df


def load_defect_table(input_dir, name, columns=None):
    path = find_table_file(input_dir, name)
    df = _normalize_keys(read_table_file(path, columns))
    log.info("Loaded %-35s rows: %s", path.name, f"{len(df):,}")
    return df


def load_intermediate(path):
    """final_intermediate.csv (Databricks: <OUTPUT_SCHEMA>.final_intermediate)."""
    if not Path(path).exists():
        raise FileNotFoundError(
            f"Intermediate table not found: {path}. Run src/code_intermediate_logic.py first "
            "or change INTERMEDIATE_PATH in utils/config.py."
        )
    df = _normalize_keys(read_table_file(path))
    df["defect_detected_on"] = to_date(df["defect_detected_on"])
    log.info("final_intermediate loaded — %s rows (from %s)", f"{len(df):,}", Path(path).name)
    return df
