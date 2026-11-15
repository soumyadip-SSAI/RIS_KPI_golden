"""Settings for the RIS trends KPI (no .env: edit the values here).

Paths are absolute, built from ROOT_DIR (the RIS_KPI_golden folder), so the pipeline can be run from any folder.
"""
from pathlib import Path

# utils -> ris_trends -> kpi_creation -> RIS_KPI_golden
ROOT_DIR = Path(__file__).resolve().parents[3]
INPUT_DATA_DIR = ROOT_DIR / "input_data"
OUTPUT_DATA_DIR = ROOT_DIR / "output_data"


# --- Input ---
# Silver tables: master_{roughness,rutting}_{parent,child_10m}, master_chainage (.parquet / .csv / .xlsx)
SILVER_INPUT_DIR = INPUT_DATA_DIR / "old_silver_data"
# Threshold mapping (Databricks: dlm_threshold_mapping_display): file name without extension, read from
# SILVER_INPUT_DIR as .parquet / .csv / .xlsx. Required.
THRESHOLD_MAPPING_TABLE = "dlm_threshold_mapping"
# True = keep only UPCs present in the contract-module project master | False = no project-master filter
FILTER_BY_PROJECT_MASTER = True
# Contract-module project master (.csv / .xlsx with a UPC/upc column). Only read when the filter is on.
PROJECT_MASTER_PATH = INPUT_DATA_DIR / "project_master.xlsx"


# --- Filters ---
# UPCs in '/' form (e.g. ["N/02015/03002/GJ", "N/07024/01001/GJ"]). Empty = all UPCs.
KEEP_UPCS = []
# "Cement concrete" is read as "Cement Concrete" before filtering (PAVEMENT_TYPE_ALIASES in utils/filters.py)
KEEP_PAVEMENT_TYPES = ["Asphalt", "Cement Concrete", "Hybrid"]
# True = Roughness_Average / Average_Rutting_Depth only from breach_flag == 1 rows
USE_BREACH_FLAG = False


# --- Output ---
# ris_trends_dw.csv is written here
OUTPUT_DIR = OUTPUT_DATA_DIR / "output_kpi_data"
RIS_TRENDS_OUTPUT_NAME = "ris_trends_dw"
