"""Settings for the KPI creation DB extraction.

DB connection settings (DB_HOST, DB_PORT, DB_NAME, DB_SCHEMA, DB_USER, DB_PASSWORD) come from ENV_FILE
(db_data_extraction/.env, template: .env.example); real environment variables override it.
defect_status_updation/utils/config.py reads the same file. Everything else is set here.

Paths are absolute, built from ROOT_DIR (the RIS_KPI_golden folder), so the extraction can be run from any folder.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# utils -> db_data_extraction -> kpi_creation -> RIS_KPI_golden
ROOT_DIR = Path(__file__).resolve().parents[3]


# --- Database (Postgres): from ENV_FILE / environment ---
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_FILE)  # does not override variables already set in the environment

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT") or 5432)
DB_NAME = os.getenv("DB_NAME")
DB_SCHEMA = os.getenv("DB_SCHEMA") or "public"
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_CONNECT_TIMEOUT = 30  # seconds


def require_db_settings():
    """Raise when a DB setting is missing (checked before connecting, so non-DB steps can import this module)."""
    missing = [name for name in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not globals()[name]]
    if missing:
        raise RuntimeError(f"Missing DB settings: {', '.join(missing)}. Add them to {ENV_FILE} "
                           "(template: .env.example) or set them as environment variables.")

# Tables pulled by db_extraction.py (add more names here to pull them too)
DB_TABLES = [
    "dlm_defect_case",
    "udm_defect_reference",
    "master_survey_system",
    "survey_data_map",
    "master_defect_type",
    "wfm_survey_schedule",
    "master_upc_project",
]


# --- DB extraction output ---
INPUT_DATA_DIR = ROOT_DIR / "input_data"
# Pulled tables land in RAW_DB_DIR/<table>/<YYYY>/<MM>/<DD>/<table>.csv (a second pull on the same day overwrites)
RAW_DB_DIR = INPUT_DATA_DIR / "raw_db_tables"
