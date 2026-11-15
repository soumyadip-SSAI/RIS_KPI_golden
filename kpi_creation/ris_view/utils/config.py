"""Settings for the RIS view (no .env: edit the values here). Three steps, run by main.py in this order:

    1. src/code_silver_table_update.py  raw_db_tables + old_silver_data -> silver_data_with_status
    2. src/code_intermediate_logic.py   old_silver_data + silver_data_with_status -> final_intermediate.csv
    3. src/code_ris_view.py             silver_data_with_status + final_intermediate.csv -> ris_view_dw.csv

Paths are absolute, built from ROOT_DIR (the RIS_KPI_golden folder), so the steps can be run from any folder.
"""
from pathlib import Path

# utils -> ris_view -> kpi_creation -> RIS_KPI_golden
ROOT_DIR = Path(__file__).resolve().parents[3]
INPUT_DATA_DIR = ROOT_DIR / "input_data"
OUTPUT_DATA_DIR = ROOT_DIR / "output_data"


# --- Filters (all steps) ---
# UPCs in '/' form (e.g. ["N/02015/03002/GJ", "N/07024/01001/GJ"]). Empty = all UPCs.
KEEP_UPCS = []


# --- Input ---
# Silver tables (master_cracking, master_pothole, master_*_parent, master_*_child_10m / _100m, master_chainage,
# reporting intervals, ...)
SILVER_INPUT_DIR = INPUT_DATA_DIR / "old_silver_data"
# DB snapshots from kpi_creation/db_data_extraction: RAW_DB_DIR/<table>/<YYYY>/<MM>/<DD>/<table>.csv
# (the latest one is used)
RAW_DB_DIR = INPUT_DATA_DIR / "raw_db_tables"
# Optional: use these files instead of the latest snapshot in RAW_DB_DIR (None = latest snapshot)
DLM_DEFECT_CASE_FILE = None
UDM_DEFECT_REFERENCE_FILE = None
# Contract-module project master (.csv / .xlsx with a UPC/upc column); also gives length / state / NH
PROJECT_MASTER_PATH = INPUT_DATA_DIR / "project_master.xlsx"
# True = keep only UPCs present in the project master | False = no project-master filter (step 3)
FILTER_BY_PROJECT_MASTER = True


# --- Sources ---
# Reporting intervals: file name without extension, read from SILVER_INPUT_DIR as .csv / .parquet / .xlsx
# (replaces the Databricks table nhai_dhms.ris_kpi_output.upc_reporting_intervals)
REPORTING_INTERVALS_TABLE = "upc_reporting_intervals"
# Interval (m) used where a reporting interval is empty or a standard (CA/IRC) has no row
DEFAULT_INTERVAL = 100
# Cracking source (file name without extension). The notebooks used the 10m table master_cracking.
CRACKING_TABLE = "master_cracking"


# --- Output ---
# Step 1 output: silver tables with defect_reference_id / current_status / final_status.
# Input of step 2 (defect ids + statuses) and step 3 (defect rows with status)
SILVER_STATUS_DIR = OUTPUT_DATA_DIR / "silver_data_with_status"
KPI_OUTPUT_DIR = OUTPUT_DATA_DIR / "output_kpi_data"
# Step 2 output, input of step 3 (Databricks: <OUTPUT_SCHEMA>.final_intermediate)
INTERMEDIATE_PATH = KPI_OUTPUT_DIR / "final_intermediate.csv"
# Step 3 output
RIS_VIEW_DW_PATH = KPI_OUTPUT_DIR / "ris_view_dw.csv"
