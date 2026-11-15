"""Settings for the RIS view defect status update flow.

DB connection settings (DB_HOST, DB_PORT, DB_NAME, DB_SCHEMA, DB_USER, DB_PASSWORD) come from ENV_FILE, the
shared kpi_creation/db_data_extraction/.env (template: .env.example next to it); real environment variables
override it. Everything else is set here.

Paths are absolute, built from ROOT_DIR (the RIS_KPI_golden folder), so the flow can be run from any folder.
The RIS view itself (inputs, outputs, filters) is configured in kpi_creation/ris_view/utils/config.py.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# utils -> defect_status_updation -> RIS_KPI_golden
ROOT_DIR = Path(__file__).resolve().parents[2]


# --- Database (Postgres): from ENV_FILE / environment ---
# Shared with kpi_creation/db_data_extraction, so the credentials live in one file
ENV_FILE = ROOT_DIR / "kpi_creation" / "db_data_extraction" / ".env"
load_dotenv(ENV_FILE)  # does not override variables already set in the environment

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT") or 5432)
DB_NAME = os.getenv("DB_NAME")
DB_SCHEMA = os.getenv("DB_SCHEMA") or "public"
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_CONNECT_TIMEOUT = 30  # seconds


def require_db_settings():
    """Raise when a DB setting is missing (checked before connecting, so the ris_view-only run still imports this)."""
    missing = [name for name in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD") if not globals()[name]]
    if missing:
        raise RuntimeError(f"Missing DB settings: {', '.join(missing)}. Add them to {ENV_FILE} "
                           "(template: .env.example) or set them as environment variables.")

# Tables read for the defect status
DEFECT_CASE_TABLE = "dlm_defect_case"
DEFECT_REFERENCE_TABLE = "udm_defect_reference"
# Tables pulled by src/db_extraction.py (add more names here to pull them too)
DB_TABLES = [DEFECT_CASE_TABLE, DEFECT_REFERENCE_TABLE]


# --- DB extraction output ---
# Pulled tables land in RAW_DB_DIR/<table>/<YYYY>/<MM>/<DD>/<table>.csv (a second pull on the same day overwrites).
# Same folder as kpi_creation/db_data_extraction, so ris_view reads the latest snapshot from here
RAW_DB_DIR = ROOT_DIR / "input_data" / "raw_db_tables"


# --- KPI code run by src/kpi_code_flow.py ---
# kpi_creation/ris_view/main.py: silver table update -> intermediate logic -> RIS view
RIS_VIEW_CODE_DIR = ROOT_DIR / "kpi_creation" / "ris_view"
RIS_VIEW_SCRIPT = "main.py"


# --- Output ---
# Written by ris_view (RIS_VIEW_DW_PATH in kpi_creation/ris_view/utils/config.py); checked here after the run
RIS_VIEW_DW_OUTPUT_PATH = ROOT_DIR / "output_data" / "output_kpi_data" / "ris_view_dw.csv"
